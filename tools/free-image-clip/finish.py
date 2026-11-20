"""finish.py in.png ref.jpg out.jpg [strength]
Free 'finishing' for AI pictures: colour match to a reference look (Lab mean/std),
local contrast, fine sharpening, film grain, output 1080x1920."""
import sys, numpy as np
from PIL import Image, ImageFilter
def srgb2lin(c): return np.where(c<=0.04045,c/12.92,((c+0.055)/1.055)**2.4)
def lin2srgb(c): return np.where(c<=0.0031308,c*12.92,1.055*np.clip(c,0,None)**(1/2.4)-0.055)
M=np.array([[0.4124,0.3576,0.1805],[0.2126,0.7152,0.0722],[0.0193,0.1192,0.9505]]); Mi=np.linalg.inv(M)
WP=np.array([0.95047,1,1.08883])
def f(t): return np.where(t>0.008856,np.cbrt(t),7.787*t+16/116)
def fi(t): return np.where(t**3>0.008856,t**3,(t-16/116)/7.787)
def rgb2lab(a):
    x=srgb2lin(a)@M.T/WP; fx=f(x)
    return np.stack([116*fx[...,1]-16,500*(fx[...,0]-fx[...,1]),200*(fx[...,1]-fx[...,2])],-1)
def lab2rgb(l):
    fy=(l[...,0]+16)/116; fx=fy+l[...,1]/500; fz=fy-l[...,2]/200
    x=np.stack([fi(fx),fi(fy),fi(fz)],-1)*WP
    return np.clip(lin2srgb(x@Mi.T),0,1)
def finish(src,ref,out,s=0.6,size=(1080,1920)):
    im=Image.open(src).convert('RGB')
    # cover-crop to 9:16 then Lanczos to final size
    w,h=im.size; tw=int(h*9/16)
    if tw<w: im=im.crop(((w-tw)//2,0,(w-tw)//2+tw,h))
    im=im.resize(size,Image.LANCZOS)
    a=np.asarray(im)/255.0; L=rgb2lab(a)
    r=rgb2lab(np.asarray(Image.open(ref).convert('RGB').resize((270,480)))/255.0)
    for c in range(3):
        m,sd=L[...,c].mean(),L[...,c].std()+1e-6; rm,rs=r[...,c].mean(),r[...,c].std()
        t=(L[...,c]-m)/sd*rs+rm
        if c==0: t=np.clip(t,0,100)
        L[...,c]=L[...,c]*(1-s)+t*s
    im=Image.fromarray((lab2rgb(L)*255).astype(np.uint8))
    im=im.filter(ImageFilter.UnsharpMask(radius=40,percent=18,threshold=0))   # local contrast ("clarity")
    im=im.filter(ImageFilter.UnsharpMask(radius=1.2,percent=70,threshold=2))  # fine detail
    g=np.random.default_rng(7).normal(0,3.2,(size[1],size[0],1))              # soft film grain
    a=np.clip(np.asarray(im).astype(float)+g,0,255).astype(np.uint8)
    Image.fromarray(a).save(out,quality=93)
if __name__=='__main__':
    finish(sys.argv[1],sys.argv[2],sys.argv[3],float(sys.argv[4]) if len(sys.argv)>4 else 0.6)
