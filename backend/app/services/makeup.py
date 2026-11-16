"""로컬 메이크업 전처리. 얼굴 사진을 저장하거나 외부 모델로 전송하지 않는다."""
import cv2
import numpy as np

BROWS = ((70,63,105,66,107,55,65,52,53,46), (336,296,334,293,300,276,283,282,295,285))
EYES = ((33,7,163,144,145,153,154,155,133,173,157,158,159,160,161,246),
        (362,382,381,380,374,373,390,249,263,466,388,387,386,385,384,398))


def _eye_mask(shape: tuple[int, int], points: np.ndarray) -> np.ndarray:
    eyes = np.zeros(shape,np.uint8)
    for indexes in EYES:
        cv2.fillPoly(eyes,[np.round(points[list(indexes)]).astype(np.int32)],255)
    return cv2.dilate(eyes,np.ones((3,3),np.uint8))


def eyebrow_mask(image: np.ndarray, points: np.ndarray) -> np.ndarray:
    h,w = image.shape[:2]
    if len(points)<468 or not np.isfinite(points).all():
        raise ValueError('유효한 얼굴 좌표가 필요합니다.')
    face_width = float(np.linalg.norm(points[234]-points[454]))
    padding = max(1,round(face_width*.009))
    mask = np.zeros((h,w),np.uint8)
    for indexes in BROWS:
        hull = cv2.convexHull(np.round(points[list(indexes)]).astype(np.int32))
        cv2.fillConvexPoly(mask,hull,255)
    mask = cv2.dilate(mask,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(padding*2+1,padding*2+1)))
    eyes = _eye_mask((h,w),points)
    mask[eyes>0]=0
    return mask


def remove_eyebrows(image: np.ndarray, points: np.ndarray) -> tuple[np.ndarray,np.ndarray]:
    mask = eyebrow_mask(image,points)
    if not mask.any():
        return image.copy(),mask
    face_width=float(np.linalg.norm(points[234]-points[454]))
    repaired=cv2.inpaint(image,mask,max(4,min(16,round(face_width*.05))),cv2.INPAINT_TELEA)
    # 앞머리와 닿은 경계가 단단한 띠로 남지 않게 보정 이미지와 알파를 함께 완화한다.
    sigma=max(1.2,min(4,face_width*.01))
    repaired=cv2.GaussianBlur(repaired,(0,0),sigma)
    alpha=np.clip(cv2.GaussianBlur(mask.astype(np.float32)/255,(0,0),sigma)*1.15,0,1)
    alpha[_eye_mask(image.shape[:2],points)>0]=0
    alpha[alpha<.004]=0
    support=(alpha>0).astype(np.uint8)*255
    alpha=alpha[...,None]
    result=np.round(image.astype(np.float32)*(1-alpha)+repaired.astype(np.float32)*alpha).astype(np.uint8)
    return result,support


def brow_regions(mask: np.ndarray, points: np.ndarray) -> dict:
    """실제로 보정한 마스크 영역을 얼굴 회전 기준 사각형으로 반환한다."""
    angle = float(np.arctan2(*(points[263]-points[33])[::-1]))
    cosine, sine = np.cos(angle), np.sin(angle)
    centers = np.array([points[list(indexes)].mean(axis=0) for indexes in BROWS])
    ys, xs = np.where(mask > 0)
    pixels = np.column_stack((xs+.5, ys+.5))
    distances = ((pixels[:, None, :]-centers[None, :, :])**2).sum(axis=2)
    sides = distances.argmin(axis=1)
    regions = {}
    for index, side in enumerate(('left', 'right')):
        region = pixels[sides == index]
        if not len(region):
            continue
        local = region @ np.array([[cosine, -sine], [sine, cosine]])
        low, high = local.min(axis=0)-.5, local.max(axis=0)+.5
        center = (low+high)/2
        regions[side] = {'x': float(center[0]*cosine-center[1]*sine),
                         'y': float(center[0]*sine+center[1]*cosine),
                         'width': float(high[0]-low[0]), 'height': float(high[1]-low[1]),
                         'angle': angle}
    return regions
