"""피부톤 측정 + 메이크업 색 계열 추천 API.

메이크업 화면 전용. 피부 분석을 거치지 않고도 사진 1장으로 바로 쓸 수 있다.
결과는 DB에 저장하지 않고, 사진은 메모리에서 분석 후 폐기한다 (기존 저장 정책과 동일).
"""

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.core.config import get_settings
from app.schemas.skin_tone import SkinToneRead, TonePalette
from app.services import makeup_palette, skin_tone
from app.services.errors import ErrorCode
from app.services.skin_analysis import AnalysisError

router = APIRouter(prefix="/skin", tags=["skin-tone"])

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_PHOTO_BYTES = 10 * 1024 * 1024


def _error(status: int, code: str, message: str, detail: dict | None = None) -> HTTPException:
    """skin.py와 같은 형태의 에러 응답. 프론트는 code로 분기한다."""
    return HTTPException(status, {"code": code, "message": message, "detail": detail or {}})


@router.post("/tone", response_model=SkinToneRead)
def analyze_skin_tone(
    file: UploadFile = File(..., description="정면 얼굴 사진 1장 (jpeg/png/webp)"),
) -> SkinToneRead:
    """사진 1장에서 피부톤(밝기 단계·언더톤)을 분류하고 어울리는 색 계열을 돌려준다.

    - 저장 없음: 사진·결과 모두 DB에 남기지 않는다.
    - 측정 불가(색이 바랜 사진, 얼굴 없음 등)는 400 + 에러 코드로 돌려보낸다.
    """
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise _error(
            415,
            ErrorCode.UNSUPPORTED_MEDIA_TYPE,
            f"지원하지 않는 형식입니다: {file.content_type}",
            {"allowed": sorted(ALLOWED_CONTENT_TYPES)},
        )
    data = file.file.read(MAX_PHOTO_BYTES + 1)
    if len(data) > MAX_PHOTO_BYTES:
        # 기존 skin.py의 밝기 측정 엔드포인트와 같은 방식 (전용 에러 코드 없음)
        raise HTTPException(413, "사진은 10MB 이하로 올려 주세요.")

    settings = get_settings()
    try:
        result = skin_tone.measure_tone(
            data,
            min_face_width=settings.min_face_width_px,
            camera_profile=settings.skin_camera_profile,  # 기기별 보정값
        )
    except AnalysisError as e:
        raise _error(400, e.code, str(e), e.detail) from e

    rec = makeup_palette.recommend(
        result.brightness_level, result.undertone, confidence=result.confidence
    )
    return SkinToneRead(
        brightness_level=result.brightness_level,
        brightness_label=skin_tone.BRIGHTNESS_LABELS[result.brightness_level],
        undertone=result.undertone,
        undertone_label=skin_tone.UNDERTONE_LABELS[result.undertone],
        confidence=result.confidence,
        palette=TonePalette(**rec["palette"]),
        notices=rec["notices"],
        raw=result.raw,
    )
