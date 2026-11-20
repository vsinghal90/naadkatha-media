"""Naad Katha free video fallback chain (18 Nov 2026).

Image-to-video from one approved still. Tries, best first:
  wan22  Wan 2.2 fast   (zerogpu-aoti/wan2-2-fp8da-aoti-faster)  up to 5 s
  wan21  Wan 2.1 fast   (multimodalart/wan2-1-fast)              short clips
  ltx    LTX-Video      (Lightricks/ltx-video-distilled)         fast, lower quality
All three are free Hugging Face ZeroGPU spaces and share ONE daily GPU allowance on the
owner's HF account. The HF token is added by the proxy (Network secret) for each space host.
Clips are silent: thunder, wind and voices go in our own mix. Prompt = motion only, one beat.

USE: python3 nk_video.py still.png prompt.txt out.mp4 [--seconds 5] [--routes wan22,ltx]
"""
import os, sys, json, time, shutil, argparse
from gradio_client import Client, handle_file

LOG = '/mnt/project-files/naad-katha-free-image-test/video-route-log.jsonl'
NEG = ("色调艳丽, 过曝, 静态, 细节模糊不清, 字幕, 最差质量, 低质量, JPEG压缩残留, 丑陋的, 残缺的, 多余的手指, 画得不好的手部, "
       "画得不好的脸部, 畸形的, 毁容的, 形态畸形的肢体, 手指融合, 静止不动的画面, 杂乱的背景, 三条腿, 背景人很多, 倒着走, "
       "face changing, extra limbs, extra tail, text, watermark, logo, subtitles, flicker")   # no 'painting' words: we want paintings
ROUTES = ['wan22', 'wan21', 'ltx']


def _client(space):
    tok = os.environ.get('HF_TOKEN')
    return Client(space, verbose=False, **({'hf_token': tok} if tok else {}))


def _path(v):
    if isinstance(v, (list, tuple)): v = v[0]
    if isinstance(v, dict): v = v.get('video') or v.get('path') or v.get('url')
    if isinstance(v, dict): v = v.get('path')
    return v


def wan22(img, prompt, secs):
    c = _client('zerogpu-aoti/wan2-2-fp8da-aoti-faster')
    r = c.predict(handle_file(img), prompt, 6, NEG, min(secs, 5.0), 1, 1, 42, True, api_name='/generate_video')
    return _path(r), 'Wan 2.2 fast'


def wan21(img, prompt, secs):
    c = _client('multimodalart/wan2-1-fast')
    r = c.predict(input_image=handle_file(img), prompt=prompt, height=896, width=512, negative_prompt=NEG,
                  duration_seconds=min(secs, 3.4), guidance_scale=1.0, steps=4, seed=42, randomize_seed=True,
                  api_name='/generate_video')
    return _path(r), 'Wan 2.1 fast'


def ltx(img, prompt, secs):
    c = _client('Lightricks/ltx-video-distilled')
    r = c.predict(prompt=prompt, negative_prompt='worst quality, inconsistent motion, blurry, jittery, distorted, face changing, text, watermark',
                  input_image_filepath=handle_file(img), input_video_filepath=None, height_ui=832, width_ui=480,
                  mode='image-to-video', duration_ui=min(secs, 8.0), ui_frames_to_use=9, seed_ui=42, randomize_seed=True,
                  ui_guidance_scale=1, improve_texture_flag=True, api_name='/image_to_video')
    return _path(r), 'LTX-Video distilled'


FN = {'wan22': wan22, 'wan21': wan21, 'ltx': ltx}


def make(img, prompt, out, secs=5.0, routes=None):
    tried = []
    for name in routes or ROUTES:
        try:
            p, model = FN[name](img, prompt, secs)
            shutil.copy(p, out)
            res = {'status': 'done', 'route': name, 'model': model, 'path': out, 'tried': tried}
            try: open(LOG, 'a').write(json.dumps({'t': time.time(), **res}) + '\n')
            except Exception: pass
            return res
        except Exception as e:
            tried.append((name, str(e)[:160]))
    raise RuntimeError('All free video routes failed (quota is shared; try tomorrow or use Gemini/Flow by hand): ' + json.dumps(tried, ensure_ascii=False))


if __name__ == '__main__':
    a = argparse.ArgumentParser()
    a.add_argument('still'); a.add_argument('prompt_file'); a.add_argument('out')
    a.add_argument('--seconds', type=float, default=5.0); a.add_argument('--routes')
    x = a.parse_args()
    print(json.dumps(make(x.still, open(x.prompt_file, encoding='utf-8').read().strip(), x.out, x.seconds,
                          x.routes.split(',') if x.routes else None), indent=1, ensure_ascii=False))
