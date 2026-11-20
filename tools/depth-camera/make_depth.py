# Depth maps for the Naad Katha 3D depth camera (free, CPU, about 1 s per picture).
# Usage: python3 make_depth.py <model.onnx> <in_dir> <out_dir> name1 [name2 ...]
# Reads <in_dir>/<name>.jpg or .png, centre-crops to 9:16, writes <out_dir>/<name>_hd.jpg (1080x1920, q82)
# and <out_dir>/<name>_d.jpg (depth map, 540x960, near = white).
# Model: Depth Anything V2 small, ONNX (models/ in this folder, or download
# https://github.com/fabio-sim/Depth-Anything-ONNX/releases/download/v2.0.0/depth_anything_v2_vits.onnx).
# Needs: pip install onnxruntime opencv-python-headless numpy
import sys, os, numpy as np, cv2, onnxruntime as ort
model, src, out, names = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:]
s = ort.InferenceSession(model, providers=['CPUExecutionProvider'])
os.makedirs(out, exist_ok=True)
for n in names:
    p = os.path.join(src, n + '.jpg')
    im = cv2.imread(p if os.path.exists(p) else os.path.join(src, n + '.png'))
    h, w = im.shape[:2]
    if w / h > 9 / 16:
        nw = int(h * 9 / 16); x0 = (w - nw) // 2; im = im[:, x0:x0 + nw]
    else:
        nh = int(w * 16 / 9); y0 = (h - nh) // 2; im = im[y0:y0 + nh]
    hd = cv2.resize(im, (1080, 1920), interpolation=cv2.INTER_LANCZOS4)
    x = cv2.resize(cv2.cvtColor(hd, cv2.COLOR_BGR2RGB), (518, 518), interpolation=cv2.INTER_CUBIC).astype(np.float32) / 255
    x = (x - np.array([0.485, 0.456, 0.406])) / np.array([0.229, 0.224, 0.225])
    d = s.run(None, {'l_x_': x.transpose(2, 0, 1)[None].astype(np.float32)})[0][0]
    d = cv2.resize(d, (540, 960), interpolation=cv2.INTER_CUBIC)
    lo, hi = np.percentile(d, 1), np.percentile(d, 99.5)
    d = np.clip((d - lo) / (hi - lo), 0, 1)
    d = cv2.dilate(d, np.ones((7, 7), np.uint8))  # grow near objects so edge stretch lands on the background
    d = cv2.GaussianBlur(d, (0, 0), 3)
    cv2.imwrite(os.path.join(out, n + '_d.jpg'), (d * 255).astype(np.uint8), [cv2.IMWRITE_JPEG_QUALITY, 92])
    cv2.imwrite(os.path.join(out, n + '_hd.jpg'), hd, [cv2.IMWRITE_JPEG_QUALITY, 82])
    print(n, 'ok, depth mean', round(float(d.mean()), 2))
