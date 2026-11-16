"""원본 눈썹 PNG를 보존하고 좌우 크롭과 썸네일을 static에 준비한다."""
from pathlib import Path
import json
import hashlib
import unicodedata
import cv2
import numpy as np
root=Path(__file__).resolve().parents[1];out=root/'static/makeup/brows';out.mkdir(parents=True,exist_ok=True)
# static에 추가한 원본을 읽고 생성된 좌우 크롭·미리보기는 제외한다.
labels={'F03_low_soft_arch':'낮은 소프트 아치','F05_low_rounded_arch':'낮은 둥근 아치','M03_full_low_angled_arch':'도톰한 각진 아치',
 'M02_natural_straight':'내추럴 일자','F06_soft_rounded_arch':'소프트 라운드 아치',
 'F08_soft_arch':'소프트 아치','F09_soft_straight':'소프트 일자',
 'M11_soft_straight':'부드러운 일자','M12_bold_straight':'짙은 일자','M13_textured_angular':'결 살린 각진','M14_airy_natural':'연한 내추럴','M15_full_soft_arch':'풍성 아치','M16_long_straight':'긴 일자','M17_natural_angular':'내추럴 각진','M18_dense_straight':'숱 많은 일자'}
# demo 스크린샷이 눈썹으로 잡히지 않게 눈썹 원본 폴더만
SOURCE_DIRS=('brows','eyebrows-face-shapes-6','brows-v2','brows-male')
sources=sorted(p for d in SOURCE_DIRS for p in (root/'static/makeup'/d).glob('*.png') if not p.stem.endswith(('-left','-right','-preview')))
if not sources:raise ValueError('static/makeup에 눈썹 원본 PNG가 없습니다.')
labels.update({'03_round_high_arch':'둥근 얼굴 · 높은 아치','04_square_crescent':'각진 얼굴 · 초승달','06_diamond_soft_arch':'마름모형 · 소프트 아치'})
groups=[(src,'남성형' if src.stem.startswith('M') or '남성' in unicodedata.normalize('NFC',src.stem) else '여성형',[(src.stem,labels.get(src.stem,src.stem))]) for src in sources]
catalog=[]
for src,group,items in groups:
 for stem,label in items:
  image=cv2.imread(str(src),cv2.IMREAD_UNCHANGED)
  if image is None or image.shape[2]!=4:raise ValueError(f'알파 채널이 필요합니다: {src}')
  h,w=image.shape[:2];sides=[]
  normalized=unicodedata.normalize('NFC',stem)
  asset_id=stem if stem.isascii() else 'M01_natural_straight'
  label=label if stem.isascii() else '자연스러운 남성 일자'
  version=hashlib.sha256(src.read_bytes()).hexdigest()[:10]
  for side,(a,b) in zip(('left','right'),((0,w//2),(w//2,w))):
   half=image[:,a:b].copy();alpha=half[:,:,3];support=(alpha>12).astype(np.uint8)
   count,components,stats,_=cv2.connectedComponentsWithStats(support);keep=np.zeros_like(support)
   for i in range(1,count):
    if stats[i,cv2.CC_STAT_AREA]>100:keep[components==i]=1
   ys,xs=np.where(keep)
   if not len(xs):raise ValueError(f'눈썹이 비었습니다: {src}')
   x0,x1=max(0,int(xs.min())-6),min(half.shape[1],int(xs.max())+7)
   y0,y1=max(0,int(ys.min())-6),min(h,int(ys.max())+7)
   crop=half[y0:y1,x0:x1];name=f'{asset_id}-{version}-{side}.png';cv2.imwrite(str(out/name),crop)
   sides.append({'url':f'/static/makeup/brows/{name}','width':crop.shape[1],'height':crop.shape[0]})
  preview=np.zeros((100,360,4),np.uint8)
  for j,side in enumerate(sides):
   crop=cv2.imread(str(out/Path(side['url']).name),cv2.IMREAD_UNCHANGED);scale=min(160/crop.shape[1],80/crop.shape[0]);small=cv2.resize(crop,None,fx=scale,fy=scale,interpolation=cv2.INTER_AREA)
   yy=(100-small.shape[0])//2;xx=j*180+(180-small.shape[1])//2;preview[yy:yy+small.shape[0],xx:xx+small.shape[1]]=small
  cv2.imwrite(str(out/f'{asset_id}-{version}-preview.png'),preview)
  catalog.append({'id':asset_id,'label':label,'group':group,'preview':f'/static/makeup/brows/{asset_id}-{version}-preview.png','left':sides[0],'right':sides[1]})
(out/'catalog.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2));print(f'{len(catalog)} eyebrow pairs prepared; source PNGs untouched')
