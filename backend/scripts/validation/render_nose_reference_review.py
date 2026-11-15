"""Run from repo root after frontend/scripts/check-nose-correction.mjs."""
from pathlib import Path
import json
import cv2
import numpy as np

root=Path('frontend/.qa-preview/contour')
rows=[]
for n in range(1,5):
    d=root/f'남{n}'
    f=json.loads((d/'face.json').read_text())
    w,h=f['width'],f['height']
    p=np.array(f['points'])*[w,h]
    def read(name):
        return np.frombuffer((d/name).read_bytes(),np.uint8).reshape(h,w,4)[:,:,:3][:,:,::-1].copy()
    original=read('source.rgba')
    shade=np.fromfile(d/'nose-reference-shade.f32',np.float32).reshape(h,w,1)
    light=np.fromfile(d/'nose-reference-light.f32',np.float32).reshape(h,w,1)
    # Diagnostic placement only, separate from the actual product render.
    alpha=np.clip(shade*.9,0,1)
    overlay=original.astype(np.float32)*(1-alpha)+np.array([65,90,125])*alpha
    alpha=np.clip(light*.85,0,1)
    overlay=np.round(overlay*(1-alpha)+255*alpha).astype(np.uint8)
    cells=[]
    c=p[4];r=np.linalg.norm(p[129]-p[358])*.90
    for label,img in [('Original',original),('Placement (diagram)',overlay),('Shading + highlight',read('nose-reference.rgba')),('Shading only 80%',read('nose-strong.rgba'))]:
        crop=img[max(0,int(p[168,1]-r*.3)):min(h,int(p[2,1]+r*.35)),max(0,int(c[0]-r)):min(w,int(c[0]+r))]
        crop=cv2.resize(crop,(320,320))
        header=np.full((36,320,3),255,np.uint8)
        cv2.putText(header,f'M{n} {label}',(8,24),cv2.FONT_HERSHEY_SIMPLEX,.49,(30,30,30),1,cv2.LINE_AA)
        cells.append(np.vstack([header,crop]))
    rows.append(np.hstack(cells))
cv2.imwrite(str(root/'nose-reference-review.jpg'),np.vstack(rows))
