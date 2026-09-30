"""피부 분석 API.

일반 흐름: (프론트) S3 업로드 → POST /api/images 로 image_id 확보
          → 로컬 브릿지에서 수분값 수신 → POST /api/skin/analyses

디버그 흐름: 사진 파일을 직접 올려 S3 없이 분석한다 (CV 임계값 조정용).
"""

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.db.session import get_db
from app.models import Image, SkinAnalysis, SkinScore
from app.schemas.skin import AnalysisCreate, AnalysisRead, MoistureSource, ScoreRead
from app.services import s3, skin_analysis, skin_scoring

router = APIRouter(prefix="/skin", tags=["skin"])

# 사진 분석이 더미로 동작한 분석을 나중에 구분할 수 있도록 버전을 달리 남긴다
DUMMY_LOGIC_VERSION = f"{skin_scoring.LOGIC_VERSION}-dummy"

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


def _get_with_scores(db: Session, analysis_id: int) -> SkinAnalysis | None:
    """점수·지표·구간을 한 번에 읽어온다.

    지연 로딩에 맡기면 지표 수만큼 추가 쿼리가 나가므로 selectinload로 묶는다.
    """
    return db.scalar(
        select(SkinAnalysis)
        .where(SkinAnalysis.id == analysis_id)
        .options(
            selectinload(SkinAnalysis.scores).selectinload(SkinScore.metric),
            selectinload(SkinAnalysis.scores).selectinload(SkinScore.category),
        )
    )


def to_read(analysis: SkinAnalysis) -> AnalysisRead:
    """응답 변환. 지표 코드 순서를 고정해 프론트에서 정렬할 필요가 없게 한다."""
    order = ("moisture", *skin_analysis.PHOTO_METRIC_CODES)
    scores = sorted(analysis.scores, key=lambda s: order.index(s.metric.code))
    return AnalysisRead(
        id=analysis.id,
        analyzed_at=analysis.analyzed_at,
        logic_version=analysis.logic_version,
        moisture_source=analysis.moisture_source,
        image_id=analysis.image_id,
        scores=[
            ScoreRead(
                metric_code=s.metric.code,
                metric_name=s.metric.name,
                score=s.score,
                category_name=s.category.name,
                higher_is_better=s.metric.higher_is_better,
            )
            for s in scores
        ],
    )


def _photo_scores(image: Image | None, seed: str) -> tuple[dict[str, int], str]:
    """사진 지표 4개를 만든다.

    S3에 원본이 있으면 실제 분석을, 없으면 더미 점수를 쓴다.
    어느 쪽이었는지는 logic_version으로 남긴다.
    """
    if image is not None and get_settings().s3_enabled:
        return (
            skin_analysis.analyze_image(s3.download_bytes(image.s3_key)),
            skin_scoring.LOGIC_VERSION,
        )
    return dict(skin_analysis.analyze_image_dummy(seed)), DUMMY_LOGIC_VERSION


def _save(
    db: Session,
    *,
    photo_scores: dict[str, int],
    logic_version: str,
    moisture_source: str,
    moisture_raw: int | None,
    moisture_score: int | None,
    guest_id=None,
    image_id: int | None = None,
) -> AnalysisRead:
    """수분 점수를 합쳐 라벨링하고 저장한다. 두 엔드포인트가 공유한다."""
    try:
        scores = skin_analysis.with_moisture(
            photo_scores,
            moisture_source=moisture_source,
            moisture_raw=moisture_raw,
            moisture_score=moisture_score,
        )
        analysis = skin_scoring.label_and_save(
            db,
            scores=scores,
            moisture_source=moisture_source,
            logic_version=logic_version,
            guest_id=guest_id,
            image_id=image_id,
        )
    except (skin_analysis.AnalysisError, skin_scoring.ScoringError) as e:
        raise HTTPException(400, str(e)) from e

    db.commit()
    return to_read(_get_with_scores(db, analysis.id))


@router.post("/analyses", status_code=201)
def create_analysis(body: AnalysisCreate, db: Session = Depends(get_db)) -> AnalysisRead:
    """사진(S3에 올린 image_id)과 수분값으로 분석 1건을 만든다."""
    image = None
    if body.image_id is not None:
        image = db.get(Image, body.image_id)
        if image is None:
            raise HTTPException(404, f"이미지를 찾을 수 없습니다: {body.image_id}")

    seed = image.s3_key if image else str(body.guest_id or body.image_id or "dev")
    photo_scores, logic_version = _photo_scores(image, seed)

    return _save(
        db,
        photo_scores=photo_scores,
        logic_version=logic_version,
        moisture_source=body.moisture_source,
        moisture_raw=body.moisture_raw,
        moisture_score=body.moisture_score,
        guest_id=body.guest_id,
        image_id=body.image_id,
    )


@router.post("/analyses/debug", status_code=201)
def create_analysis_debug(
    file: UploadFile = File(..., description="정면 얼굴 사진 (jpeg/png/webp)"),
    moisture_source: MoistureSource = Form("none"),
    moisture_raw: int | None = Form(None),
    moisture_score: int | None = Form(None),
    db: Session = Depends(get_db),
) -> AnalysisRead:
    """사진을 직접 올려 분석한다 (S3를 거치지 않음).

    CV 임계값을 맞출 때 쓰는 개발용 경로다. 원본은 저장하지 않으므로
    image_id는 항상 null이 된다.
    """
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            400, f"지원하지 않는 형식입니다: {file.content_type} (jpeg/png/webp만 가능)"
        )

    try:
        photo_scores = skin_analysis.analyze_image(file.file.read())
    except skin_analysis.AnalysisError as e:
        raise HTTPException(400, str(e)) from e

    return _save(
        db,
        photo_scores=photo_scores,
        logic_version=skin_scoring.LOGIC_VERSION,
        moisture_source=moisture_source,
        moisture_raw=moisture_raw,
        moisture_score=moisture_score,
    )


@router.get("/analyses/{analysis_id}")
def get_analysis(analysis_id: int, db: Session = Depends(get_db)) -> AnalysisRead:
    analysis = _get_with_scores(db, analysis_id)
    if analysis is None:
        raise HTTPException(404, f"분석 결과를 찾을 수 없습니다: {analysis_id}")
    return to_read(analysis)
