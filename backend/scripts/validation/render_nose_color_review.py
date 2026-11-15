"""Compare existing vs sampled nose shadow colors after check-nose-correction.mjs."""
from pathlib import Path
import json
import cv2
import numpy as np

root=Path('frontend/.qa-preview/contour');rows=[]
for n in range(1,5):
 d=root/f'남{n}';f=json.loads((d/'face.json').read_text());palette=json.loads((d/'nose-palette.json').read_text());w,h=f['width'],f['height'];p=np.array(f['points'])*[w,h];cells=[];c=p[4];r=np.linalg.norm(p[129]-p[358])*.9
 for label,file in [('Original','source.rgba'),('Previous color','nose-before-color.rgba'),('Sampled nose color','nose-reference.rgba')]:
  img=np.fromfile(d/file,np.uint8).reshape(h,w,4)[:,:,:3][:,:,::-1].copy();crop=img[max(0,int(p[168,1]-r*.3)):min(h,int(p[2,1]+r*.35)),max(0,int(c[0]-r)):min(w,int(c[0]+r))];crop=cv2.resize(crop,(340,320));header=np.full((36,340,3),255,np.uint8);cv2.putText(header,f'M{n} {label}',(8,24),cv2.FONT_HERSHEY_SIMPLEX,.52,(30,30,30),1,cv2.LINE_AA);cells.append(np.vstack([header,crop]))
 row=np.hstack(cells);footer=np.full((44,row.shape[1],3),255,np.uint8)
 for x,key,text in [(8,'skinHex','Nose skin'),(300,'shadowHex','Nose shadow')]:
  color=tuple(int(palette[key][i:i+2],16) for i in (5,3,1));cv2.rectangle(footer,(x,7),(x+42,35),color,-1);cv2.putText(footer,f'{text} {palette[key]}',(x+52,28),cv2.FONT_HERSHEY_SIMPLEX,.5,(30,30,30),1,cv2.LINE_AA)
 rows.append(np.vstack([row,footer]))
cv2.imwrite(str(root/'nose-color-review.jpg'),np.vstack(rows))
