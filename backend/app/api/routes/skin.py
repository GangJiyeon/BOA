"""피부 분석 API

사진 파일을 직접 받아 분석 후 저장 (사진은 저장 안 함)
"""

from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import Actor, require_analysis_actor, require_owned_result
from app.core.config import get_settings
from app.db.session import get_db
from app.models import SkinAnalysis, SkinScore
from app.schemas.skin import AnalysisRead, DebugAnalysisRead, MoistureSource, ScoreRead
from app.services import quota, skin_analysis, skin_scoring
from app.services.errors import ErrorCode
from app.services.moisture_scale60 import classification

router = APIRouter(prefix="/skin", tags=["skin"])

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


def _error(status: int, code: str, message: str, detail: dict | None = None) -> HTTPException:
    """프론트가 코드로 분기할 수 있는 형태로 에러를 만든다.

    응답 본문: {"detail": {"code": ..., "message": ..., "detail": {...}}}
    메시지 문구는 바뀔 수 있으므로 프론트는 code로 분기해야 한다.
    """
    return HTTPException(status, {"code": code, "message": message, "detail": detail or {}})


def _get_with_scores(db: Session, analysis_id: int) -> SkinAnalysis | None:
    """점수·지표·구간을 한 번에 읽어온다.

    지연 로딩에 맡기면 지표 수만큼 추가 쿼리가 나가므로 selectinload로 묶는다.
    """
    return db.scalar(
        select(SkinAnalysis)
        .where(SkinAnalysis.id == analysis_id)
        .options(
            selectinload(SkinAnalysis.moisture_observations),
            selectinload(SkinAnalysis.scores).selectinload(SkinScore.metric),
            selectinload(SkinAnalysis.scores).selectinload(SkinScore.category),
        )
    )


def to_read(analysis: SkinAnalysis) -> AnalysisRead:
    """응답 변환. 지표 코드 순서를 고정해 프론트에서 정렬할 필요가 없게 한다."""
    order = ("moisture", *skin_analysis.PHOTO_METRIC_CODES)
    scores = sorted(analysis.scores, key=lambda s: order.index(s.metric.code))
    from app.services.moisture import observation_receipt
    observation = observation_receipt(max(analysis.moisture_observations, key=lambda r: (datetime.fromisoformat(r.payload["measured_at"].replace("Z", "+00:00")), r.id))) if analysis.moisture_observations else None
    effective = [ScoreRead(metric_code=s.metric.code, metric_name=s.metric.name, score=s.score,
                           category_name=s.category.name, higher_is_better=s.metric.higher_is_better) for s in scores]
    if observation and observation.used_for_scoring:
        effective = [s for s in effective if s.metric_code != 'moisture']
        effective.insert(0, ScoreRead(metric_code='moisture', metric_name=observation.score_metric_name,
            score=observation.normalized_score if observation.normalized_score is not None else observation.calibrated_score, category_name=observation.score_category, higher_is_better=True))
    return AnalysisRead(
        moisture_measurement=observation,
        id=analysis.id,
        analyzed_at=analysis.analyzed_at,
        logic_version=analysis.logic_version,
        moisture_source="sensor" if observation and observation.used_for_scoring else analysis.moisture_source,
        image_id=analysis.image_id,
        scores=effective,
    )


def _save(
    db: Session,
    *,
    photo_scores: dict[str, int],
    logic_version: str,
    moisture_source: str,
    moisture_raw: int | None,
    moisture_score: int | None,
    user_id: int | None = None,
    guest_id=None,
    image_id: int | None = None,
) -> AnalysisRead:
    """수분 점수를 합쳐 라벨링하고 저장한다."""
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
            user_id=user_id,
            guest_id=guest_id,
            image_id=image_id,
        )
    except (skin_analysis.AnalysisError, skin_scoring.ScoringError) as e:
        raise _error(400, e.code, str(e), e.detail) from e

    db.commit()
    return to_read(_get_with_scores(db, analysis.id))


@router.post("/analyses/debug", status_code=201)
def create_analysis_debug(
    file: UploadFile = File(..., description="정면 얼굴 사진 (jpeg/png/webp)"),
    moisture_source: MoistureSource = Form("none"),
    moisture_raw: int | None = Form(None),
    moisture_score: int | None = Form(None),
    manual_moisture_index: int | None = Form(None, ge=0, le=60),
    actor: Actor = Depends(require_analysis_actor),
    db: Session = Depends(get_db),
) -> DebugAnalysisRead:
    """사진을 올려 분석 후 저장 (프론트 피부 분석이 쓰는 실제 경로)

    원본 사진은 저장 안 함 → image_id는 항상 null, 응답에 정규화 전 원시값(raw) 포함
    """
    quota.check_quota(db, actor, "skin")
    if manual_moisture_index is not None:
        if moisture_source != "manual" or moisture_score is not None or moisture_raw is not None:
            raise HTTPException(422, "수동 수분 지수는 다른 수분값과 함께 보낼 수 없습니다.")
        category = classification(manual_moisture_index)["estimation_category"]
        metric = skin_scoring._load_metrics(db, {"moisture"}).get("moisture")
        ranges = skin_scoring._load_categories(db, [metric.id]).get(metric.id, []) if metric else []
        matched = [r for r in ranges if r.name == category]
        if len(matched) != 1:
            raise HTTPException(500, "수분 판정 구간을 확인해 주세요.")
        # Preserve the sensor category while storing a compatible legacy score.
        lo, hi = {"개선 필요": (0, 19), "보통": (20, 49), "양호": (50, 60)}[category]
        band = matched[0]
        moisture_score = band.min_score + round(
            (manual_moisture_index - lo) * (band.max_score - band.min_score) / (hi - lo)
        )

    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise _error(
            400,
            ErrorCode.UNSUPPORTED_MEDIA_TYPE,
            f"지원하지 않는 형식입니다: {file.content_type} (jpeg/png/webp만 가능)",
            {"content_type": file.content_type, "allowed": sorted(ALLOWED_CONTENT_TYPES)},
        )

    try:
        photo_scores, raw = skin_analysis.analyze_image_detail(
            file.file.read(),
            min_face_width=get_settings().min_face_width_px,
            camera_profile=get_settings().skin_camera_profile,  # 기기별 보정값
        )
    except skin_analysis.AnalysisError as e:
        raise _error(400, e.code, str(e), e.detail) from e

    saved = _save(
        db,
        photo_scores=photo_scores,
        logic_version=skin_scoring.LOGIC_VERSION,
        moisture_source=moisture_source,
        moisture_raw=moisture_raw,
        moisture_score=moisture_score,
        user_id=actor.user_id,
        guest_id=actor.guest_id,
    )
    return DebugAnalysisRead(**saved.model_dump(), raw=raw)


@router.get("/analyses/{analysis_id}")
def get_analysis(analysis_id: int, actor: Actor = Depends(require_analysis_actor), db: Session = Depends(get_db)) -> AnalysisRead:
    analysis = _get_with_scores(db, analysis_id)
    require_owned_result(analysis, actor)
    return to_read(analysis)
