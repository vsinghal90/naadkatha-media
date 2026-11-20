"""Run INSIDE the Composio workbench (our container cannot reach aihorde.net).
Free AI Horde helpers used in the 16 Nov 2026 test. Anonymous key: max about 1 megapixel per job
(768x1344 is fine; 1088x1920 needs ~262 kudos upfront), so full size comes from: AI upscale x2,
Lanczos down to 1088x1920, then optional 3-strip img2img redraw (Flux only; Z-Image img2img broke)."""
import requests,base64,io,time,numpy as np
from PIL import Image
H={'apikey':'0000000000','Client-Agent':'nk-test:1:anon','Content-Type':'application/json'}
STY=" Style: cinematic devotional painting, smooth realistic Indian mythological art, rich gold, deep indigo and ember tones, dramatic volumetric light, epic scale, theatrical chiaroscuro, highly detailed. Vertical 9:16 full-bleed composition. No text, no letters, no frames, no borders, no watermark."
PAINT="Oil painting with visible brush strokes. "   # put in FRONT for Z-Image so it paints instead of photographing
def submit(prompt,model='Z-Image-Turbo',w=768,h=1344,steps=9,cfg=1,src=None,den=None):
    # Z-Image-Turbo: steps 9. Flux.1-Schnell fp8 (Compact): steps 4. Sleep 1.1 s between submits (2/s limit).
    p={'width':w,'height':h,'steps':steps,'cfg_scale':cfg,'sampler_name':'k_euler','n':1}
    if den: p['denoising_strength']=den
    b={'prompt':prompt,'params':p,'models':[model],'nsfw':False,'censor_nsfw':True,'r2':True,'slow_workers':True}
    if src: b['source_image']=src; b['source_processing']='img2img'
    r=requests.post('https://aihorde.net/api/v2/generate/async',headers=H,json=b,timeout=60); return r.status_code,r.json()
def status(i): return requests.get(f'https://aihorde.net/api/v2/generate/status/{i}',timeout=20).json()
def upscale(img_url,form='RealESRGAN_x2plus'):
    r=requests.post('https://aihorde.net/api/v2/interrogate/async',headers=H,json={'forms':[{'name':form}],'source_image':img_url},timeout=30)
    return r.json()['id']   # poll /v2/interrogate/status/<id>, about 1 min
TILES=[0,480,960]          # 3 full-width strips 1088x960 (under the 1 MP cap), 480 px overlap
def strips(base1088,prompt,model='Flux.1-Schnell fp8 (Compact)',den=0.35):
    ids=[]
    for y in TILES:
        b=io.BytesIO(); base1088.crop((0,y,1088,y+960)).save(b,'WEBP',quality=95)
        ids.append(submit(prompt,model,1088,960,4,src=base64.b64encode(b.getvalue()).decode(),den=den)[1]['id']); time.sleep(1.1)
    return ids
def stitch(base1088,tiles):
    acc=np.zeros((1920,1088,3)); wt=np.zeros((1920,1088,1))
    for y,t in zip(TILES,tiles):
        t=np.asarray(t.convert('RGB').resize((1088,960))).astype(float); r=np.ones(960)
        if y>0: r[:240]=np.linspace(0,1,240)
        if y+960<1920: r[-240:]=np.linspace(1,0,240)
        acc[y:y+960]+=t*r[:,None,None]; wt[y:y+960]+=r[:,None,None]
    return Image.fromarray((acc/np.maximum(wt,1e-6)).clip(0,255).astype(np.uint8))
