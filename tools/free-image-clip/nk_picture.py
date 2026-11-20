"""Naad Katha picture fallback chain (17 Nov 2026).

Tries the free picture routes in quality order and falls back to the next one when a
route is out of quota, has no key, cannot be reached or fails. A route that runs out of
quota is parked in a state file until its reset time, so later pictures skip it at once.

WHERE TO RUN: in our own container (hosts allowed 17 Nov 2026). Keys are saved by the owner as
Network secrets (the proxy adds them, so the script never sees them); an environment variable
works too (Composio workbench). A route whose key is missing gets a 401 and is skipped.

  HF_TOKEN            Hugging Face read token        (routes hf_zimage, hf_flux)
  POLLINATIONS_KEY    Pollinations secret key        (route pollinations_zimage)
  CF_ACCOUNT_ID + CF_API_TOKEN  Cloudflare Workers AI (route cloudflare_flux)
  GEMINI_API_KEY      Google AI Studio key           (route gemini; free image quota is 0
                      today, so it only works once billing or a free quota exists)

USE (workbench cells time out at 60 s, so run it in a thread and poll `job`):
  exec(open('nk_picture.py').read())
  job = start(prompt_text, '/home/user/out/scene01.png')   # returns at once
  ... later: print(job)   -> {'status': 'done', 'route': 'hf_zimage', 'path': ..., 'tried': [...]}
Or blocking (outside the workbench): make(prompt_text, out_path)

Every result is 9:16. Then: Horde RealESRGAN x2 (or none for 1152x2048 routes), Lanczos to
1080x1920, then finish.py, as in the picture-maker skill.
Locked characters (Ravan, Sita, Brahma, series regulars) do NOT use this chain: they stay
on the Canva reference-picture route.
"""
import os, io, re, json, time, base64, threading, urllib.parse
import requests

STATE = os.environ.get('NK_ROUTE_STATE', '/mnt/project-files/naad-katha-free-image-test/route-state.json')
LOG = os.environ.get('NK_ROUTE_LOG', '/mnt/project-files/naad-katha-free-image-test/route-log.jsonl')
W, H = 768, 1344          # 9:16 base size that every free route accepts

# Quality order, best first. Same model on several hosts: the host with the bigger
# picture or the faster queue goes first.
ROUTES = ['gemini', 'hf_zimage', 'pollinations_zimage', 'horde_zimage',
          'cloudflare_flux', 'hf_flux']


class Quota(Exception):
    """Route is out of quota; park it until `until` (epoch seconds)."""
    def __init__(self, msg, until=None):
        super().__init__(msg); self.until = until or time.time() + 3600


class Skip(Exception):
    """Route cannot run now (no key, not reachable); try the next one."""


def _state():
    try: return json.load(open(STATE))
    except Exception: return {}


def _park(route, until, why):
    s = _state(); s[route] = {'until': until, 'why': why[:200]}
    json.dump(s, open(STATE, 'w'))


def _parked(route):
    v = _state().get(route)
    return v and v['until'] > time.time()


def _retry_after(text, default=3600):
    m = re.search(r'(\d+)h(\d+)m', text) or re.search(r'(\d+):(\d+):(\d+)', text)
    if m:
        g = [int(x) for x in m.groups()]
        wait = g[0] * 3600 + g[1] * 60 + (g[2] if len(g) > 2 else 0)
        if wait > 60: return time.time() + wait
    return time.time() + default


def _quota_check(code, text):
    t = text.lower()
    if code in (402, 429) or 'quota' in t or 'exceeded' in t or 'insufficient' in t or 'rate limit' in t:
        raise Quota(f'{code} {text[:160]}', _retry_after(text))
    if code in (401, 403):
        raise Skip(f'{code} key refused: {text[:120]}')


# ---------- routes ----------
def r_gemini(prompt, out):
    key = os.environ.get('GEMINI_API_KEY')
    hdr = {'Content-Type': 'application/json'}
    if key: hdr['x-goog-api-key'] = key   # in our container the proxy adds the saved key
    body = {'contents': [{'parts': [{'text': prompt}]}],
            'generationConfig': {'responseModalities': ['IMAGE'], 'imageConfig': {'aspectRatio': '9:16'}}}
    for model in ('gemini-3.1-flash-image', 'gemini-2.5-flash-image'):
        try:
            r = requests.post(f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent',
                              headers=hdr, json=body, timeout=180)
        except requests.RequestException as e:
            raise Skip(f'not reachable: {e}')
        if r.status_code != 200:
            try: _quota_check(r.status_code, r.text)
            except Quota:
                if model == 'gemini-2.5-flash-image': raise
                continue
            raise Skip(f'{r.status_code} {r.text[:120]}')
        for p in r.json()['candidates'][0]['content']['parts']:
            if 'inlineData' in p:
                open(out, 'wb').write(base64.b64decode(p['inlineData']['data'])); return model
        raise Skip('no image in reply (safety block?)')


def _hf_client(space):
    from gradio_client import Client
    tok = os.environ.get('HF_TOKEN')    # else the Network secret on huggingface.co / *.hf.space is used
    try: return Client(space, hf_token=tok, verbose=False) if tok else Client(space, verbose=False)
    except TypeError: return Client(space, token=tok, verbose=False)


def _hf_err(e):
    t = str(e)
    if 'quota' in t.lower(): raise Quota(t[:200], _retry_after(t, 3600))
    raise Skip(t[:200])


def _save_any(p, out):
    from PIL import Image
    if isinstance(p, dict): p = p.get('path') or p.get('url')
    Image.open(p).convert('RGB').save(out)


def r_hf_zimage(prompt, out):
    c = _hf_client('Tongyi-MAI/Z-Image-Turbo')
    try:
        r = c.predict(prompt=prompt, resolution='1152x2048 ( 9:16 )', seed=7, steps=9, shift=3.0,
                      random_seed=True, gallery_images=[], api_name='/generate')
    except Exception as e: _hf_err(e)
    g = r[0]; item = g[0] if isinstance(g, list) else g
    _save_any(item['image'] if isinstance(item, dict) and 'image' in item else item, out)
    return 'Z-Image-Turbo 1152x2048 (HF Space)'


def r_hf_flux(prompt, out):
    c = _hf_client('black-forest-labs/FLUX.1-schnell')
    try:
        r = c.predict(prompt=prompt, seed=0, randomize_seed=True, width=W, height=H,
                      num_inference_steps=4, api_name='/infer')
    except Exception as e: _hf_err(e)
    _save_any(r[0], out); return 'FLUX.1-schnell (HF Space)'


def r_pollinations_zimage(prompt, out):
    key = os.environ.get('POLLINATIONS_KEY', 'proxy')   # 'proxy' = Network secret adds the real key
    url = (f'https://gen.pollinations.ai/image/{urllib.parse.quote(prompt)}'
           f'?model=zimage&width={W}&height={H}&nologo=true&seed={int(time.time()) % 100000}')
    try: r = requests.get(url, headers={'Authorization': f'Bearer {key}'}, timeout=180)
    except requests.RequestException as e: raise Skip(f'not reachable: {e}')
    if r.status_code != 200 or 'image' not in r.headers.get('content-type', ''):
        _quota_check(r.status_code, r.text); raise Skip(f'{r.status_code} {r.text[:120]}')
    open(out, 'wb').write(r.content); return 'Z-Image-Turbo (Pollinations)'


HORDE = {'apikey': os.environ.get('HORDE_KEY', '0000000000'), 'Client-Agent': 'naadkatha:1:anon',
         'Content-Type': 'application/json'}


def r_horde_zimage(prompt, out, max_wait=1800):
    b = {'prompt': prompt, 'params': {'width': W, 'height': H, 'steps': 9, 'cfg_scale': 1,
         'sampler_name': 'k_euler', 'n': 1}, 'models': ['Z-Image-Turbo'], 'nsfw': False,
         'censor_nsfw': True, 'r2': True, 'slow_workers': True}
    try: r = requests.post('https://aihorde.net/api/v2/generate/async', headers=HORDE, json=b, timeout=60)
    except requests.RequestException as e: raise Skip(f'not reachable: {e}')
    if r.status_code != 202: _quota_check(r.status_code, r.text); raise Skip(r.text[:160])
    jid, t0 = r.json()['id'], time.time()
    while time.time() - t0 < max_wait:
        time.sleep(15)
        s = requests.get(f'https://aihorde.net/api/v2/generate/status/{jid}', timeout=30).json()
        if s.get('faulted'): raise Skip('Horde job faulted')
        if s.get('done'):
            g = s['generations'][0]
            if g.get('censored'): raise Skip('Horde NSFW filter censored it (reword, or hands-only close-up)')
            open(out, 'wb').write(requests.get(g['img'], timeout=60).content)
            return f'Z-Image-Turbo (AI Horde, {int(time.time() - t0)} s)'
    requests.delete(f'https://aihorde.net/api/v2/generate/status/{jid}', timeout=30)
    raise Skip(f'Horde queue longer than {max_wait} s')


def r_cloudflare_flux(prompt, out):
    acct, tok = os.environ.get('CF_ACCOUNT_ID'), os.environ.get('CF_API_TOKEN', 'proxy')
    if not acct: raise Skip('no CF_ACCOUNT_ID (environment variable, not secret)')
    base = f'https://api.cloudflare.com/client/v4/accounts/{acct}/ai/run/@cf/black-forest-labs/'
    hdr = {'Authorization': f'Bearer {tok}'}
    # FLUX.2 [klein] takes width/height (multipart); FLUX.1 schnell is square only, so it is the backup.
    try:
        r = requests.post(base + 'flux-2-klein-4b', headers=hdr, timeout=180,
                          files={'prompt': (None, prompt), 'width': (None, str(W)), 'height': (None, str(H))})
        if r.status_code == 200:
            open(out, 'wb').write(base64.b64decode(r.json()['result']['image'])); return 'FLUX.2 klein (Cloudflare)'
        _quota_check(r.status_code, r.text)
        r = requests.post(base + 'flux-1-schnell', headers=hdr, json={'prompt': prompt, 'steps': 8}, timeout=180)
    except requests.RequestException as e: raise Skip(f'not reachable: {e}')
    if r.status_code != 200: _quota_check(r.status_code, r.text); raise Skip(r.text[:160])
    open(out, 'wb').write(base64.b64decode(r.json()['result']['image']))
    return 'FLUX.1 schnell (Cloudflare, square: crop to 9:16)'


FN = {'gemini': r_gemini, 'hf_zimage': r_hf_zimage, 'pollinations_zimage': r_pollinations_zimage,
      'horde_zimage': r_horde_zimage, 'cloudflare_flux': r_cloudflare_flux, 'hf_flux': r_hf_flux}


def make(prompt, out, routes=None):
    """Try each route in order. Returns {'route','model','path','tried'}; raises if all fail."""
    tried = []
    for name in routes or ROUTES:
        if _parked(name):
            tried.append((name, 'parked: ' + _state()[name]['why'][:80])); continue
        try:
            model = FN[name](prompt, out)
            res = {'status': 'done', 'route': name, 'model': model, 'path': out, 'tried': tried}
            open(LOG, 'a').write(json.dumps({'t': time.time(), **res}) + '\n')
            return res
        except Quota as e:
            _park(name, e.until, str(e)); tried.append((name, 'quota: ' + str(e)[:100]))
        except Skip as e:
            tried.append((name, 'skip: ' + str(e)[:100]))
        except Exception as e:
            tried.append((name, 'error: ' + str(e)[:100]))
    raise RuntimeError('All free routes failed. Last resort: Canva generate-image (by hand). ' + json.dumps(tried))


def start(prompt, out, routes=None):
    """Run make() in a background thread (for the Composio workbench). Poll the returned dict."""
    job = {'status': 'running', 'path': out}
    def go():
        try: job.update(make(prompt, out, routes))
        except Exception as e: job.update(status='failed', error=str(e)[:600])
    threading.Thread(target=go, daemon=True).start()
    return job


def routes_now():
    """Which routes are usable right now (key present, not parked)."""
    need = {'hf_zimage': [], 'pollinations_zimage': [], 'cloudflare_flux': ['CF_ACCOUNT_ID'],
            'gemini': [], 'horde_zimage': [], 'hf_flux': []}
    return {r: ('parked' if _parked(r) else 'missing ' + ','.join(k for k in need[r] if not os.environ.get(k))
                if any(not os.environ.get(k) for k in need[r]) else 'ready') for r in ROUTES}


if __name__ == '__main__':
    import argparse
    a = argparse.ArgumentParser(description='Make one Naad Katha picture down the free route chain.')
    a.add_argument('prompt_file'); a.add_argument('out')
    a.add_argument('--routes', help='comma list to override the order, e.g. horde_zimage,hf_flux')
    a.add_argument('--status', action='store_true', help='print which routes are ready, then exit')
    x = a.parse_args()
    if x.status: print(json.dumps(routes_now(), indent=1)); raise SystemExit
    print(json.dumps(make(open(x.prompt_file).read().strip(), x.out, x.routes.split(',') if x.routes else None), indent=1))
