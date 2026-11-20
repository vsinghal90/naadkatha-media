# relight.py <src_up.jpg> <out_hd.jpg> <style> [beam=x0,x1,y1,width]   styles: night, dark, mist, warm, dawn, firstdawn
# coolsat=0.3 keeps only 30% of the blue/teal saturation (for a cold picture turning warm)
# keephue: keep the source picture's colours and take only the new brightness (stops an orange sari turning yellow)
# beam: a soft warm shaft of first light from the top edge at x0 down to (x1,y1), all as 0-1 fractions; width as a fraction of frame width
# Grades a picture to its scene-sheet light (replaces the old all-dark grade2), centre-crops 9:16, writes 1080x1920.
import sys, numpy as np, cv2
from PIL import Image
src, out, st = sys.argv[1:4]
im = cv2.cvtColor(np.array(Image.open(src).convert('RGB')), cv2.COLOR_RGB2BGR)
h, w = im.shape[:2]; tw = int(round(h * 9 / 16))
if w > tw: x0 = (w - tw) // 2; im = im[:, x0:x0 + tw]
else: th = int(round(w * 16 / 9)); y0 = (h - th) // 2; im = im[y0:y0 + th]
im = cv2.resize(im, (1080, 1920), interpolation=cv2.INTER_LANCZOS4)
f = im.astype(np.float32) / 255
P = {  # black point, gamma (<1 lifts), knee, gain, sat, vignette, tint BGR, lift
 'night': (0.015, 0.84, 0.86, 1.06, 1.00, 0.20, (1.00, 1.00, 1.02), 0.0),
 'dark':  (0.03, 0.95, 0.80, 1.00, 0.98, 0.28, (1.02, 1.00, 1.00), 0.0),
 'mist':  (0.0, 0.88, 0.90, 1.00, 0.70, 0.10, (1.02, 1.00, 0.98), 0.07),
 'warm':  (0.01, 0.80, 0.90, 1.06, 1.05, 0.15, (0.90, 1.00, 1.07), 0.0),
 'dawn':  (0.0, 0.74, 0.92, 1.08, 1.06, 0.08, (0.88, 1.01, 1.08), 0.02),
 'firstdawn': (0.01, 0.80, 0.88, 1.04, 1.05, 0.16, (0.80, 0.98, 1.14), 0.0)}
bp, gam, knee, gain, sat, vig, tint, lift = P[st]
for a in sys.argv[4:]:
    if a.startswith('coolsat='):   # take the blue/teal out of a cold picture before warming it (first light arriving)
        hsv = cv2.cvtColor((f * 255).astype(np.uint8), cv2.COLOR_BGR2HSV).astype(np.float32)
        cool = np.clip(1 - np.abs(hsv[..., 0] - 102) / 28, 0, 1)
        hsv[..., 1] *= 1 - cool * (1 - float(a[8:]))
        f = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR).astype(np.float32) / 255
f = np.clip((f - bp) / (1 - bp), 0, 1) ** gam * gain
f = np.where(f > knee, knee + (f - knee) * 0.55, f)
f = f * np.array(tint, np.float32)
lum = (0.114 * f[..., 0] + 0.587 * f[..., 1] + 0.299 * f[..., 2])[..., None]
f = lum + (f - lum) * sat
f = lift + f * (1 - lift)
yy, xx = np.mgrid[0:1920, 0:1080].astype(np.float32)
r = np.sqrt(((xx - 540) / 648) ** 2 + ((yy - 864) / 1152) ** 2)
f *= (1 - vig * np.clip(r - 0.5, 0, 1) ** 1.3)[..., None]
T = {'night': 22, 'dark': 16, 'mist': 35, 'warm': 32, 'dawn': 45, 'firstdawn': 30}[st]
def Lm(x): return cv2.cvtColor((np.clip(x, 0, 1) * 255).astype(np.uint8), cv2.COLOR_BGR2LAB)[..., 0].mean() * 100 / 255
g = 1.0
while Lm(np.clip(f, 0, 1) ** g) < T and g > 0.55: g -= 0.03   # lift only, never darken
f = np.clip(f, 0, 1) ** g
for a in sys.argv[4:]:
    if a.startswith('beam='):   # soft warm shaft of first light, screen-blended
        x0, x1, y1, bw = [float(v) for v in a[5:].split(',')]
        t = np.clip(yy / (y1 * 1920), 0, 1)
        cx = (x0 + (x1 - x0) * t) * 1080; half = bw * 1080 * (0.6 + 0.6 * t)
        m = np.exp(-((xx - cx) / half) ** 2) * (yy <= y1 * 1920 * 1.08) * (0.55 + 0.45 * t)
        pool = np.exp(-(((xx - x1 * 1080) / (bw * 1080 * 2.2)) ** 2 + ((yy - y1 * 1920 * 1.1) / (0.07 * 1920)) ** 2))
        m = cv2.GaussianBlur((m + 0.8 * pool).astype(np.float32), (0, 0), 25)[..., None]
        col = np.array([0.30, 0.64, 1.0], np.float32)          # BGR warm gold
        f = 1 - (1 - f) * (1 - np.clip(m * 0.72, 0, 1) * col)
o = (np.clip(f, 0, 1) * 255).astype(np.uint8)
if 'keephue' in sys.argv[4:]:   # keep the source colours (e.g. Sita's saffron sari), take only the new brightness
    lo = cv2.cvtColor(o, cv2.COLOR_BGR2LAB).astype(np.float32); ls = cv2.cvtColor(im, cv2.COLOR_BGR2LAB).astype(np.float32)
    lo[..., 1:] = 128 + (ls[..., 1:] - 128) * 1.04
    o = cv2.cvtColor(np.clip(lo, 0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR)
cv2.imwrite(out, o, [cv2.IMWRITE_JPEG_QUALITY, 88])
L = cv2.cvtColor(o, cv2.COLOR_BGR2LAB)[..., 0].astype(np.float32) * 100 / 255
print(out, st, 'L mean %.1f p90 %.1f' % (L.mean(), np.percentile(L, 90)))
