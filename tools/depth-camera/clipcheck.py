"""Clip motion check. Run on EVERY final mp4 before upload. Fails if an AI clip is frozen in the mp4.
Usage: python3 clipcheck.py <final.mp4> <timeline.json> <shots.js> <folder with the v_*.mp4 clips> [PART]
For each shot marked vid:1 it takes the final mp4 frame near the end of the shot and checks it looks more like the
source clip at that same moment than like the clip's first frame. Exit code 1 and a FAIL line if any clip is frozen."""
import sys,re,json,subprocess,numpy as np
mp4,tlf,shf,cdir=sys.argv[1:5]; part=sys.argv[5] if len(sys.argv)>5 else None
T=json.load(open(tlf,encoding='utf-8')); part=part or list(T)[0]; T=T[part]; L={l['k']:l for l in T['lines']}
def dur(f): return float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',f]))
def fr(f,t):
    r=subprocess.run(['ffmpeg','-v','error','-ss',f'{max(0,t):.3f}','-i',f,'-frames:v','1','-vf','scale=72:128,format=gray','-f','rawvideo','-'],capture_output=True).stdout
    return np.frombuffer(r,dtype=np.uint8).astype(np.float32) if len(r)==72*128 else None
shots=[]
for m in re.finditer(r"\{from:'(\w+)'(.*?)(?=\n\s*\{from:|\Z)",open(shf,encoding='utf-8').read(),re.S):
    k,body=m.group(1),m.group(2); at=re.search(r"\bat:([\d.]+)",body); img=re.search(r"img:'(\w+)'",body)
    shots.append({'k':k,'t0':float(at.group(1)) if at else L[k]['s'],'img':img.group(1) if img else '','vid':bool(re.search(r"\bvid:1",body))})
bad=0; n=0
for i,s in enumerate(shots):
    if not s['vid']: continue
    n+=1; t1=shots[i+1]['t0'] if i+1<len(shots) else T['total']; src=f"{cdir}/{s['img']}.mp4"; d=dur(src)
    x=min(t1-s['t0'],d)-0.4
    if x<0.6: print('SKIP (too short)',s['img']); continue
    a=fr(mp4,s['t0']+x); b=fr(src,x); c=fr(src,0)
    if a is None or b is None or c is None: print('FAIL (no frame)',s['img']); bad+=1; continue
    move=float(np.abs(b-c).mean()); dn=float(np.abs(a-b).mean()); d0=float(np.abs(a-c).mean())
    ok = move<2.0 or dn<d0
    print(('OK  ' if ok else 'FAIL FROZEN'),s['img'],f"shot {s['t0']:.1f}-{t1:.1f}s  like-clip-now {dn:.1f}  like-first-frame {d0:.1f}  clip motion {move:.1f}")
    bad+=0 if ok else 1
print(f"{n} clips checked, {bad} frozen"); sys.exit(1 if bad or n==0 and '--allow-none' not in sys.argv else 0)
