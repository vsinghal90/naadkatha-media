// Naad Katha depth camera recorder: records the approved preview page frame by frame to JPEGs,
// so the MP4 is exactly what the owner OK'd. Run it ONLY when the Short is ready for posting.
// Usage: ROOT=<folder holding index.html and a/> PORT=8800 node record.js <outdir> <fps> [startSec] [endSec]
// The page must support ?rec=1 (1080x1920 #stage, UI hidden) and expose window.__ready(), window.__frame(t), window.__total.
// On 4 CPUs run 4 chunks at once (different PORTs, ranges 0-30, 30-60, 60-90, 90-end), then mux:
// ffmpeg -framerate 30 -i <outdir>/%05d.jpg -i mix.wav -c:v libx264 -crf 18 -pix_fmt yuv420p -c:a aac -b:a 192k -shortest -movflags +faststart out.mp4
const { chromium } = require('playwright');
const http = require('http'), fs = require('fs'), path = require('path');
const root = process.env.ROOT || process.cwd();
const port = +(process.env.PORT || 8766);
const types = {'.html':'text/html; charset=utf-8','.jpg':'image/jpeg','.png':'image/png','.mp3':'audio/mpeg','.wav':'audio/wav','.mp4':'video/mp4','.webm':'video/webm'};
const srv = http.createServer((q, r) => { const f = path.join(root, decodeURIComponent(q.url.split('?')[0])); fs.readFile(f, (e, d) => { if (e) { r.writeHead(404); r.end(); return } const ct = types[path.extname(f)] || 'application/octet-stream'; const m = /bytes=(\d*)-(\d*)/.exec(q.headers.range || '');
  /* Range support is REQUIRED: without it a <video> cannot seek, every AI clip freezes on its first frame in the mp4 (Tulsi Short, 20 Nov 2026). */
  if (m) { const a = m[1] ? +m[1] : 0, b = m[2] ? Math.min(+m[2], d.length - 1) : d.length - 1; r.writeHead(206, {'Content-Type': ct, 'Accept-Ranges': 'bytes', 'Content-Range': 'bytes ' + a + '-' + b + '/' + d.length, 'Content-Length': b - a + 1}); r.end(d.subarray(a, b + 1)); return }
  r.writeHead(200, {'Content-Type': ct, 'Accept-Ranges': 'bytes', 'Content-Length': d.length}); r.end(d) }) }).listen(port, '127.0.0.1');
(async () => {
  const [out, fpsS, a, b] = process.argv.slice(2); const fps = +fpsS || 30; fs.mkdirSync(out, {recursive: true});
  const br = await chromium.launch(); const p = await br.newPage({viewport: {width: 1080, height: 1920}, deviceScaleFactor: 1});
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto('http://127.0.0.1:' + port + '/index.html?rec=1');
  await p.waitForFunction(() => window.__ready && window.__ready(), null, {timeout: 60000});
  await p.evaluate(() => document.fonts.ready);
  const total = await p.evaluate(() => window.__total); const t0 = +a || 0, t1 = Math.min(+b || total, total);
  const st = await p.$('#stage'); const n0 = Math.round(t0 * fps), n1 = Math.round(t1 * fps); const start = Date.now();
  for (let n = n0; n < n1; n++) { await p.evaluate(t => window.__frame(t), n / fps); await st.screenshot({path: path.join(out, String(n).padStart(5, '0') + '.jpg'), type: 'jpeg', quality: 92}); }
  console.log('frames', n1 - n0, 'sec/frame', ((Date.now() - start) / 1000 / (n1 - n0)).toFixed(3), 'errors', JSON.stringify(errs));
  await br.close(); srv.close();
})();
