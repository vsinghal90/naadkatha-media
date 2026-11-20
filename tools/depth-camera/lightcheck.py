"""Light and music check for a Naad Katha preview, against the approved scene sheet.

Usage:
  python3 lightcheck.py <frames_dir> <shots.json> <scene_sheet.json> [--music score.wav] [--part C]

frames_dir   frames from shotcheck.js: <part>_<ii>_<j>.jpg (j = 0 start, 1 middle, 2 end of shot ii)
shots.json   [[i, t0, t1, img], ...]  (shotcheck.js prints this list; save it to a file)
scene_sheet  [{"at": 0, "beat": "Hook", "light": "night"}, ...]  light = one of the LIGHT keys below;
             a beat may set its own "min", "max" or "lit" (e.g. a closing under the end card)
--music      the music bed alone (no voice). Checks that the music really changes at each sheet turn.

Prints one line per shot (beat, light word, frame brightness, lit-subject brightness, PASS/LOW/HIGH/FLAT)
and the arc checks. Exit code 1 if anything fails, so it can gate a render.
Brightness is mean luma on a 0 to 100 scale, measured on the rendered frames (grade, captions and all).
"""
import sys, json, os
import numpy as np
from PIL import Image

# allowed mean brightness of the whole frame for each light word
LIGHT = {
    'night':     (14, 34),   # moonlit, but faces readable
    'dark':      (10, 28),   # dark court, cold throne room
    'mist':      (26, 56),   # soft grey legend, unreal
    'redgold':   (18, 48),   # firelight, threat
    'warm':      (22, 52),   # warm gold, Sita's fire
    'firstdawn': (20, 52),   # first light breaks in
    'dawn':      (35, 72),   # bright gold dawn (the Aha)
    'sunrise':   (35, 72),   # closing
    'day':       (40, 80),
}
# 90th percentile luma of the frame: something in it must be clearly lit (a face, a flame, the sky).
# Mist is soft on purpose, so its floor is lower.
LIT = {'night': 38, 'dark': 34, 'mist': 30, 'redgold': 40, 'warm': 40, 'firstdawn': 40, 'dawn': 50, 'sunrise': 45, 'day': 50}
DAWN_GAP = 12       # dawn/sunrise shots must be this much brighter than the darkest beat's shots


def luma(path):
    a = np.asarray(Image.open(path).convert('L').resize((270, 480)), dtype=np.float32) / 2.55
    return float(a.mean()), float(np.percentile(a, 90))


def beat_at(sheet, t):
    cur = sheet[0]
    for b in sheet:
        if b['at'] <= t + 1e-6: cur = b
    return cur


def music_turns(wav, sheet):
    import wave
    w = wave.open(wav); sr = w.getframerate(); ch = w.getnchannels(); sw = w.getsampwidth()
    raw = w.readframes(w.getnframes())
    x = np.frombuffer(raw, dtype={2: np.int16, 4: np.int32}[sw]).astype(np.float32)
    x = x.reshape(-1, ch).mean(1) / (2 ** (8 * sw - 1))
    out = []
    for b in sheet[1:]:
        t = b['at']; n = int(3 * sr); i = int(t * sr)
        A, B = x[max(0, i - n):i], x[i:i + n]
        if len(A) < sr or len(B) < sr: continue
        def feat(s):
            rms = 20 * np.log10(np.sqrt(np.mean(s ** 2)) + 1e-9)
            S = np.abs(np.fft.rfft(s * np.hanning(len(s)))); f = np.fft.rfftfreq(len(s), 1 / sr)
            cen = float((S * f).sum() / (S.sum() + 1e-9))
            bands = np.array([S[(f >= lo) & (f < hi)].sum() for lo, hi in [(30, 120), (120, 400), (400, 1500), (1500, 6000)]])
            return rms, cen, bands / (bands.sum() + 1e-9)
        ra, ca, ba = feat(A); rb, cb, bb = feat(B)
        d_rms = rb - ra; d_cen = (cb - ca) / max(ca, 1); d_band = float(np.abs(bb - ba).sum())
        changed = abs(d_rms) >= 2.5 or abs(d_cen) >= 0.15 or d_band >= 0.18
        out.append((t, b['beat'], round(d_rms, 1), round(d_cen * 100), round(d_band, 2), changed))
    return out


def main():
    a = sys.argv[1:]
    music = part = None
    if '--music' in a: k = a.index('--music'); music = a[k + 1]; del a[k:k + 2]
    if '--part' in a: k = a.index('--part'); part = a[k + 1]; del a[k:k + 2]
    frames, shots, sheet = a[0], json.load(open(a[1])), json.load(open(a[2]))
    sheet = sorted(sheet, key=lambda b: b['at'])
    part = part or 'C'
    fails = 0; rows = []
    print(f"{'shot':>4} {'time':>11}  {'picture':<14} {'beat':<22} {'light':<9} {'frame':>5} {'lit':>5}  result")
    for i, t0, t1, img in shots:
        mid = (t0 + t1) / 2; b = beat_at(sheet, mid)
        lo, hi = b.get('min', LIGHT[b['light']][0]), b.get('max', LIGHT[b['light']][1]); floor = b.get('lit', LIT[b['light']])
        # the middle frame is the shot itself; start and end frames can sit inside a crossfade
        p = os.path.join(frames, f'{part}_{i:02d}_1.jpg')
        if not os.path.exists(p): print(f'{i:>4} missing frames'); fails += 1; continue
        m, p90 = luma(p)
        res = 'PASS'
        if m < lo: res = 'LOW'
        elif m > hi: res = 'HIGH'
        if p90 < floor: res = (res + ' + FLAT') if res != 'PASS' else 'FLAT (nothing clearly lit)'
        if res != 'PASS': fails += 1
        rows.append((i, b['light'], m))
        print(f'{i:>4} {t0:5.1f}-{t1:5.1f}  {img:<14} {b["beat"][:22]:<22} {b["light"]:<9} {m:5.1f} {p90:5.1f}  {res}  (allowed {lo}-{hi})')
    # arc: the light must actually rise at the end
    by = {}
    for i, l, m in rows: by.setdefault(l, []).append(m)
    darkest = min(np.mean(v) for k, v in by.items() if k not in ('dawn', 'sunrise', 'day'))
    for k in ('dawn', 'sunrise'):
        if k in by:
            ok = np.mean(by[k]) >= darkest + DAWN_GAP
            print(f"arc: {k} shots {np.mean(by[k]):.1f} vs darkest beat {darkest:.1f}: {'PASS' if ok else 'FAIL, the ending is not brighter'}")
            fails += 0 if ok else 1
    if music:
        print('\nmusic at each turn (3 s before vs 3 s after): loudness change dB, brightness change %, band shift')
        for t, beat, dr, dc, db, ch in music_turns(music, sheet):
            print(f"  {t:6.1f}s {beat:<22} {dr:+5.1f} dB {dc:+4d}% {db:4.2f}  {'changes' if ch else 'SAME (music does not turn here)'}")
            fails += 0 if ch else 1
    print('\nRESULT:', 'PASS' if not fails else f'{fails} problem(s)')
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
