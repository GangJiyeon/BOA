"""메이크업 체험용 얼굴 랜드마크 (AI 호출 없음, 사진 저장 안 함)

브라우저가 이 좌표로 쉐딩·하이라이터·블러셔·립 위치를 잡고 색은 브라우저에서 계산
"""
import base64

import cv2

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from app.api.deps import require_analysis_actor
from app.services import hair_studio, makeup as makeup_service
from app.services.cheek_analysis import calculate_cheek_ratio, makeup_cheek_features
from app.services.face_shape_analysis import analyze_face_shape
from app.services.landmark_extraction import LANDMARK_INDEX_MAP
from app.services.nose_shape_analysis import analyze_nose_shape, makeup_nose_strengths

router = APIRouter(prefix="/makeup", tags=["makeup"])

MAX_PHOTO_BYTES = 10 * 1024 * 1024


class FaceLandmarks(BaseModel):
    points: list[tuple[float, float]]  # 478점, 사진 크기 대비 0~1


class FaceFeatures(BaseModel):
    """쉐딩·하이라이터 배치용 얼굴형·코·광대 분석 (팀 분석 모듈 결과 그대로)"""
    face_shape: str
    face_ratios: dict[str, float]
    nose_tags: list[str]
    nose_ratios: dict[str, float]
    nose_correction: dict[str, float]
    cheek_width_ratio: float
    cheek_correction: dict[str, float]


class MakeupPreparation(FaceLandmarks):
    brow_regions: dict[str, dict[str, float]]
    features: FaceFeatures | None = None
    brow_base_png: str
    width: int
    height: int


def _features(points) -> FaceFeatures | None:
    """얼굴형·코 모양·광대 폭 분석, 실패하면 없이 (쉐딩은 기본 배치로)"""
    named={name:(float(points[i][0]),float(points[i][1])) for name,i in LANDMARK_INDEX_MAP.items()}
    try:
        nose=analyze_nose_shape(named)
        face=analyze_face_shape([named],source='single')
        return FaceFeatures(face_shape=face['face_shape'],face_ratios=face['ratios'],nose_tags=nose['nose_tags'],nose_ratios=nose['ratios'],nose_correction=makeup_nose_strengths(nose['ratios']),cheek_width_ratio=calculate_cheek_ratio(named)['cheek_width_ratio'],cheek_correction=makeup_cheek_features(named))
    except ValueError:
        return None


def _prepare(data: bytes) -> MakeupPreparation:
    image=hair_studio.decode_image(data,max_side=1280)
    h,w=image.shape[:2]
    points=hair_studio.landmarks(image)
    cleaned,mask=makeup_service.remove_eyebrows(image,points)
    ok,encoded=cv2.imencode('.png',cleaned)
    if not ok:
        raise ValueError('눈썹 보정 이미지를 만들지 못했습니다.')
    return MakeupPreparation(points=[(float(x)/w,float(y)/h) for x,y in points],features=_features(points),
        brow_base_png=base64.b64encode(encoded.tobytes()).decode(),brow_regions=makeup_service.brow_regions(mask,points),width=w,height=h)


@router.post('/prepare',dependencies=[Depends(require_analysis_actor)])
async def prepare_makeup(photo: UploadFile=File(...)) -> MakeupPreparation:
    data=await photo.read()
    if len(data)>MAX_PHOTO_BYTES:
        raise HTTPException(413,'사진은 10MB 이하로 올려 주세요')
    try:
        return await run_in_threadpool(_prepare,data)
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc
