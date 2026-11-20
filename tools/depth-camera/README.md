# Naad Katha 3D depth camera (default motion, owner 14 Nov 2026)

Every approved still moves like a real camera inside the painting: push-in, drone fly-over, orbit, vertigo dolly-zoom, a close-up cut from the same picture, a small tremble on fear lines and a jolt on drum hits, with a colour grade per turn and light particles (dust, wind, embers, ash, gold motes). Faces never change, because only pixels shift. Free: runs on CPU, no credits.

First used on the Arjun ghabrahat Short (v12 ready; post date open since the owner moved it off 15 Nov 2026, so its folder is parked until a date is set). Its full build, with the mix scripts: /mnt/project-files/naad-katha-posts/arjun-ghabrahat-short_parked/dramatic/

## Files
- make_depth.py: HD still (1080x1920) and depth map (540x960) for each picture, about 1 s each.
- template.html: the preview page (WebGL depth camera, key-line captions, grade, particles, music, switches). The same page is recorded for the MP4, so the preview equals the final.
- page.py: fills the template with timeline.json (from the mix) and the caption text of every line.
- record.js: frame recorder for the final MP4.
- models/depth_anything_v2_vits.onnx: the depth model, 99 MB (or download https://github.com/fabio-sim/Depth-Anything-ONNX/releases/download/v2.0.0/depth_anything_v2_vits.onnx ; GitHub release files are reachable, Hugging Face is not).

## Steps
1. Pictures approved by the owner (9:16), one file per beat (hands.jpg, armies.jpg ...).
2. Depth maps: `pip install onnxruntime opencv-python-headless numpy`, then `python3 make_depth.py models/depth_anything_v2_vits.onnx <stills> <preview>/a hands armies ...`. Look at a contact sheet of the depth maps: near things white, sky and far walls dark.
3. Voice and music mix first. The mix script writes timeline.json: every line key with its start `s` and end `e` in seconds, plus `total`.
4. Copy template.html and set, per video:
   - `SHOTS`: one per beat, `{from: <first line key>, img: <picture>, mv: <move>, trem: [fear line keys], cut: true for a hard cut}`.
   - Moves (function `cam`): hook, drone, fear, vertigo, orbit, close, glow, soft, soft2, end. Each sets centre `cx, cy`, zoom `z`, depth strength `k`, focus depth `f` and parallax `ox, oy`.
   - `HITS`: hits in seconds for the camera jolt, empty by default. Add one ONLY where the viewer clearly hears a hit (a drum, a conch blast, a thud) at that moment, checked in the final mix on a phone speaker. Owner, 20 Nov 2026, Arjun Short: "i dont hear the war-drum and thus the shaking is useless" (the drums sat under the narration), so a shake without a heard hit reads as a glitch.
   - `GRADE`: `[saturation, brightness, contrast]` per move. `PT`: particles per move.
   - `KEY`: the lines shown on screen (hook, shlok with its source, Aha, end card), Devanagari only (brand kit).
   - The audio file name (`const au`) and the source label (`#src`).
5. In page.py set `CAP` (Hinglish) and `HI` (Devanagari) for every line key, then `python3 page.py template.html <preview>/index.html`.
6. Publish `<preview>` as an HTML preview page (artifact) for the owner. Every change is made and shown on the preview.
7. Only when the Short is ready for posting (owner OK on the final preview, pre-upload check passed, post slot set), record and encode:
   - `ROOT=<preview> PORT=8800 node record.js frames 30 0 30`, and at the same time `30 60`, `60 90`, `90 <end>` on ports 8830, 8860, 8890.
   - `ffmpeg -framerate 30 -i frames/%05d.jpg -i mix_norm.wav -c:v libx264 -crf 18 -pix_fmt yuv420p -c:a aac -b:a 192k -shortest -movflags +faststart out.mp4`
   - About 8 to 13 minutes for a 2 minute Short on 4 CPUs.

## Gotchas
- Second faces (found 14 Nov 2026 on the Arjun Short, Krishna in the Aha shot): the first shader solved each pixel with a 6-step fixed-point loop, which at depth edges could land on a copy from behind and draw a second face. template.html now marches from the nearest depth to the farthest and keeps the FIRST surface it hits (32 steps plus 6 refining steps), so the front always wins. Never go back to the old loop. Still look at every face at the start, middle and end of each shot before the preview goes out.
- A clear 3D feel needs the depth strength k to CHANGE during the shot (near things grow or slide against the background). A plain zoom with a fixed k reads as flat (owner, 14 Nov: "why is the 3D effect applied to only one shot?").
- record.js starts its own local web server inside node. A separate background python server was blocked by the auto-mode check.
- Headless Chromium has WebGL with the default launch. Do not add unsafe GPU flags.
- Captions, grade and fades are driven by time, never by the clock, so the recording matches the preview frame for frame.
- No em dash, en dash or double hyphen in any on-screen text (brand kit).

## Light and music check (added 16 Nov 2026, Lanka Bhag 3)
- relight.py <src_up.jpg> <out_hd.jpg> <style> [coolsat=0.25] [beam=x0,x1,y1,width]: grades a picture to its scene-sheet light (night, dark, mist, warm, dawn, firstdawn). It only lifts exposure, never darkens. coolsat takes the blue out of a cold picture before warming it; beam adds a soft shaft of first light.
- lightcheck.py <frames_dir> <shots.json> <scene_sheet.json> [--music score.wav]: run after shotcheck.js (which writes <part>_shots.json). Checks each shot's brightness against its beat's light word, that something in every frame is clearly lit, that the ending is brighter than the darkest beat, and that the music really changes at each turn. Exit 1 on any problem.
- Scene sheet example: lanka-dramatic-test/build3d-bhag3-maryada/build/scene_sheet_C.json.

## Clips must play in the mp4 (added 20 Nov 2026, after the Tulsi Short went out with 6 frozen clips)
- record.js now answers Range requests (206). Without them a `<video>` cannot seek, so every AI clip stays on its first frame in the recording even though the preview plays fine. Never record with a server that lacks Range support (old copy: _old/record_no-range_201126.js).
- After EVERY final mux, before any upload: `python3 clipcheck.py <final.mp4> <timeline.json> <shots.js> <folder with the v_*.mp4 clips>`. It must print "0 frozen" (exit 0). A FAIL blocks the upload: fix, re-record, check again.
- Also look at a contact sheet with 3 frames INSIDE each clip shot (start, middle, end), not one frame per shot.
