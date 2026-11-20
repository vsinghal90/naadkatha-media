# Video tools (shared)

Free tools used to build Naad Katha Shorts. Other projects (for example Shuddh Desi Bites) can copy them as they are. No keys, tokens or media are stored here: every key is read from an environment variable or added by a network proxy at run time.

Needs: Python 3 with `numpy pillow opencv-python-headless onnxruntime gradio_client requests`, Node with `playwright` (Chromium), and `ffmpeg`/`ffprobe` on the PATH.

## depth-camera/  (3D camera moves on still pictures, preview, recording, checks)

Full step by step guide: [depth-camera/README.md](depth-camera/README.md).

| File | What it does | How to run |
|---|---|---|
| `make_depth.py` | Makes a depth map for each still (Depth Anything V2 small, about 1 s per picture on CPU). | `python3 make_depth.py <model.onnx> <stills folder> <out folder> name1 name2 ...` |
| `template.html` | The preview page: WebGL depth camera (push-in, orbit, drone, dolly zoom), captions, colour grade, particles, music, seek bar. The same page is recorded for the mp4, so preview = final. | Edit its `SHOTS`, `KEY` and timeline, then build with `page.py`. |
| `page.py` | Fills the template with the captions and timeline and writes the preview `index.html`. | `python3 page.py template.html <preview>/index.html` |
| `relight.py` | Grades a picture to its scene light (night, dark, mist, warm, dawn, firstdawn), crops 9:16, writes 1080x1920. | `python3 relight.py in.jpg out.jpg warm` |
| `lightcheck.py` | Checks each shot's brightness (and optionally that the music changes) against the scene sheet. | `python3 lightcheck.py <frames> shots.json scene_sheet.json [--music score.wav]` |
| `record.js` | **Preview recorder.** Opens the preview in headless Chromium and saves every frame as JPEG. Serves files with HTTP Range and `video/mp4`, which is required: without it AI video clips cannot seek and freeze on their first frame. | `ROOT=<preview folder> PORT=8800 node record.js <frames out> 30 [start] [end]`, then mux with the ffmpeg line at the top of the file. |
| `clipcheck.py` | **Frozen-clip checker.** Run on every final mp4 before upload. For each AI clip shot it checks the mp4 really moves like the source clip. Exit code 1 and a FAIL line if any clip is frozen. | `python3 clipcheck.py final.mp4 timeline.json shots.js <clips folder>` (must end with "0 frozen") |

The depth model (99 MB) is not in the repo. Download it from
https://github.com/fabio-sim/Depth-Anything-ONNX/releases/download/v2.0.0/depth_anything_v2_vits.onnx

## free-image-clip/  (free picture and video-clip routes)

| File | What it does | How to run |
|---|---|---|
| `nk_picture.py` | Picture fallback chain, best first: Gemini, HF Z-Image, Pollinations, AI Horde, Cloudflare Flux, HF Flux. A route out of quota is parked and the next one is tried. | `python3 nk_picture.py prompt.txt out.png`, or `--status` to see which routes are usable. |
| `nk_video.py` | Image-to-video fallback chain on free Hugging Face spaces: Wan 2.2, Wan 2.1, LTX-Video. Clips are silent. | `python3 nk_video.py still.png prompt.txt out.mp4 [--seconds 5] [--routes wan22,ltx]` |
| `horde_free.py` | Small helpers for the free AI Horde API (anonymous key, about 1 megapixel per job). | Import it or read it as an example. |
| `finish.py` | Free finishing for AI pictures: colour match to a reference, local contrast, sharpening, film grain, 1080x1920 output. | `python3 finish.py in.png ref.jpg out.jpg [strength]` |

Keys (set as environment variables, or as proxy-added secrets, never in code): `HF_TOKEN`, `POLLINATIONS_KEY`, `CF_ACCOUNT_ID` + `CF_API_TOKEN`, `GEMINI_API_KEY`, optional `HORDE_KEY`. A route with no key is skipped.

Log paths: `nk_picture.py` writes its state and log under `/mnt/project-files/naad-katha-free-image-test/` by default; set `NK_ROUTE_STATE` and `NK_ROUTE_LOG` to use your own folder. `nk_video.py` has its log path in the `LOG` line near the top; change it to your folder.
