"""Local QA fixtures for frontend/scripts/check-auto-contour.mjs. Run from the repository root."""
import sys,json,unicodedata
from pathlib import Path
import cv2,numpy as np,mediapipe as mp
sys.path.insert(0,str(Path('backend').resolve()))
from app.services.landmark_extraction import LANDMARK_INDEX_MAP
from app.services.face_shape_analysis import analyze_face_shape
from app.services.nose_shape_analysis import analyze_nose_shape, makeup_nose_strengths
from app.services.cheek_analysis import calculate_cheek_ratio, makeup_cheek_features
out=Path('frontend/.qa-preview/contour')
with mp.solutions.face_mesh.FaceMesh(static_image_mode=True,max_num_faces=1,refine_landmarks=True) as mesh:
 for path in Path('backend/ref').glob('*.jpg'):
  name=unicodedata.normalize('NFC',path.stem)
  if name not in ['남1','남2','남3','남4']:continue
  img=cv2.imread(str(path));h,w=img.shape[:2];img=cv2.resize(img,(round(w*min(1,800/max(w,h))),round(h*min(1,800/max(w,h)))))
  h,w=img.shape[:2];res=mesh.process(cv2.cvtColor(img,cv2.COLOR_BGR2RGB));assert res.multi_face_landmarks,name
  points=np.array([(p.x*w,p.y*h) for p in res.multi_face_landmarks[0].landmark]);named={k:tuple(points[i]) for k,i in LANDMARK_INDEX_MAP.items()}
  face=analyze_face_shape([named],source='single');nose=analyze_nose_shape(named)
  features={'cheek_correction':makeup_cheek_features(named),'nose_correction':makeup_nose_strengths(nose['ratios']),**nose['ratios'],**calculate_cheek_ratio(named),'face_shape':face['face_shape'],'face_ratios':face['ratios']}
  d=out/name;d.mkdir(exist_ok=True);(d/'face.json').write_text(json.dumps(dict(width=w,height=h,points=(points/[w,h]).tolist(),features=features),ensure_ascii=False))
  rgba=cv2.cvtColor(img,cv2.COLOR_BGR2RGBA);(d/'source.rgba').write_bytes(rgba.tobytes());cv2.imwrite(str(d/'original.png'),img)
  print(name,json.dumps(features,ensure_ascii=False))
