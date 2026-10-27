"""피부 분석 API.

일반 흐름: (프론트) S3 업로드 → POST /api/images 로 image_id 확보
          → 로컬 브릿지에서 수분값 수신 → POST /api/skin/analyses

디버그 흐름: 사진 파일을 직접 올려 S3 없이 분석한다 (CV 임계값 조정용).
재현성 측정: 같은 사람 사진 여러 장을 한 번에 올려 반복 측정 통계를 본다.
"""

import statistics

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.db.session import get_db
from app.models import Image, SkinAnalysis, SkinScore
from app.schemas.skin import (
    AnalysisCreate,
    AnalysisRead,
    DebugAnalysisRead,
    MoistureSource,
    RepeatabilityMetric,
    RepeatabilityPhoto,
    RepeatabilityRejected,
    RepeatabilityReport,
    ScoreRead,
)
from app.services import s3, skin_analysis, skin_scoring
from app.services.errors import ErrorCode

router = APIRouter(prefix="/skin", tags=["skin"])

# 사진 분석이 더미로 동작한 분석을 나중에 구분할 수 있도록 버전을 달리 남긴다
DUMMY_LOGIC_VERSION = f"{skin_scoring.LOGIC_VERSION}-dummy"

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}

# ── 재현성 측정 설정 ───────────────────────────────────────────────
# 한 번에 올릴 수 있는 사진 수 (통계를 내려면 최소 2장)
REPEATABILITY_MIN_FILES = 2
REPEATABILITY_MAX_FILES = 20

# 지표별로 통계를 낼 원시값과 합격 판단 방식
# (지표 코드, 원시값 키, 판단 방식)
REPEATABILITY_METRICS = (
    ("redness", "redness_index", "cv"),
    ("brightness", "mean_l_skin", "cv"),
    ("uniformity", "std_l_skin", "cv"),
    # 트러블 비율은 대개 0 근처라 변동계수가 수백 %로 부풀어 의미가 없다.
    # 그래서 점수가 몇 점 범위에서 움직였는지로 판단한다.
    ("trouble", "blemish_ratio", "score_range"),
)

# 합격 기준: 변동계수 10% 이하 / 점수 변동 폭 10점 이하
REPEATABILITY_MAX_CV = 10.0
REPEATABILITY_MAX_SCORE_RANGE = 10

# 평균이 이보다 작으면 변동계수를 계산하지 않는다 (0으로 나누기·과대 추정 방지)
REPEATABILITY_CV_MIN_MEAN = 1e-3

# 분석 부위 이름 (재현성 리포트에서 사진별 사용 부위를 뽑을 때 사용)
REGION_NAMES = tuple(name for name, _, _ in skin_analysis.REGIONS)


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
            skin_analysis.analyze_image(
                s3.download_bytes(image.s3_key),
                min_face_width=get_settings().min_face_width_px,
            ),
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
        raise _error(400, e.code, str(e), e.detail) from e

    db.commit()
    return to_read(_get_with_scores(db, analysis.id))


@router.post("/analyses", status_code=201)
def create_analysis(body: AnalysisCreate, db: Session = Depends(get_db)) -> AnalysisRead:
    """사진(S3에 올린 image_id)과 수분값으로 분석 1건을 만든다."""
    image = None
    if body.image_id is not None:
        image = db.get(Image, body.image_id)
        if image is None:
            raise _error(
                404,
                ErrorCode.IMAGE_NOT_FOUND,
                f"이미지를 찾을 수 없습니다: {body.image_id}",
                {"image_id": body.image_id},
            )

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
) -> DebugAnalysisRead:
    """사진을 직접 올려 분석한다 (S3를 거치지 않음).

    CV 임계값을 맞출 때 쓰는 개발용 경로다. 원본은 저장하지 않으므로
    image_id는 항상 null이 된다. 응답에는 정규화 전 원시값(raw)이 함께 담긴다.
    """
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise _error(
            400,
            ErrorCode.UNSUPPORTED_MEDIA_TYPE,
            f"지원하지 않는 형식입니다: {file.content_type} (jpeg/png/webp만 가능)",
            {"content_type": file.content_type, "allowed": sorted(ALLOWED_CONTENT_TYPES)},
        )

    try:
        photo_scores, raw = skin_analysis.analyze_image_detail(
            file.file.read(), min_face_width=get_settings().min_face_width_px
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
    )
    return DebugAnalysisRead(**saved.model_dump(), raw=raw)


@router.get("/analyses/{analysis_id}")
def get_analysis(analysis_id: int, db: Session = Depends(get_db)) -> AnalysisRead:
    analysis = _get_with_scores(db, analysis_id)
    if analysis is None:
        raise _error(
            404,
            ErrorCode.ANALYSIS_NOT_FOUND,
            f"분석 결과를 찾을 수 없습니다: {analysis_id}",
            {"analysis_id": analysis_id},
        )
    return to_read(analysis)


# ── 재현성 측정 (디버그) ─────────────────────────────────────────────


def _load_category_lookup(db: Session) -> dict[str, list]:
    """지표 코드별 판정 구간 목록을 읽어온다 (분석 결과는 DB에 저장하지 않는다)."""
    metrics = skin_scoring._load_metrics(db, set(skin_analysis.PHOTO_METRIC_CODES))
    categories = skin_scoring._load_categories(db, [m.id for m in metrics.values()])
    return {code: categories.get(metric.id, []) for code, metric in metrics.items()}


def _summarize_metric(
    metric_code: str, raw_key: str, judged_by: str, photos: list[RepeatabilityPhoto]
) -> RepeatabilityMetric:
    """지표 하나에 대해 사진들의 원시값·점수·판정을 모아 통계를 낸다."""
    values = [p.raw[raw_key] for p in photos]
    scores = [p.scores[metric_code] for p in photos]
    categories = sorted({p.categories[metric_code] for p in photos})

    # 원시값의 평균·표준편차·변동계수
    raw_mean = statistics.fmean(values)
    raw_std = statistics.stdev(values) if len(values) >= 2 else 0.0
    cv = (
        raw_std / abs(raw_mean) * 100
        if abs(raw_mean) >= REPEATABILITY_CV_MIN_MEAN
        else None
    )

    # 점수 변동 폭
    score_range = max(scores) - min(scores)

    # 합격 판단: 지표 특성에 맞는 기준 하나를 쓴다
    if judged_by == "cv":
        passed = cv is not None and cv <= REPEATABILITY_MAX_CV
    else:
        passed = score_range <= REPEATABILITY_MAX_SCORE_RANGE

    return RepeatabilityMetric(
        metric_code=metric_code,
        raw_key=raw_key,
        raw_mean=round(raw_mean, 4),
        raw_std=round(raw_std, 4),
        raw_cv_percent=None if cv is None else round(cv, 2),
        score_min=min(scores),
        score_max=max(scores),
        score_range=score_range,
        categories=categories,
        category_agreed=len(categories) == 1,
        judged_by=judged_by,
        passed=passed,
    )


@router.post("/analyses/debug/repeatability")
def check_repeatability_debug(
    files: list[UploadFile] = File(
        ...,
        description="같은 사람을 같은 조건에서 찍은 정면 사진 2~20장 (jpeg/png/webp)",
        # Swagger UI는 배열 항목이 format=binary일 때만 파일 선택칸을 그린다.
        # (FastAPI 기본 스키마의 contentMediaType으로는 글자 입력칸이 나온다)
        json_schema_extra={"items": {"type": "string", "format": "binary"}},
    ),
    db: Session = Depends(get_db),
) -> RepeatabilityReport:
    """같은 사람 사진 여러 장을 분석해 재현성(반복 측정 시 흔들림)을 계산한다.

    개발용 경로다. 분석 결과는 DB에 저장하지 않는다.
    - 지표별 원시값의 평균·표준편차·변동계수, 점수 변동 폭, 판정 일치 여부
    - 사진마다 분석에 쓰인 부위가 같은지 (앞머리 등으로 일부 사진만 이마가 빠졌는지)
    """
    # 1) 사진 개수 확인
    if not REPEATABILITY_MIN_FILES <= len(files) <= REPEATABILITY_MAX_FILES:
        raise _error(
            400,
            ErrorCode.INVALID_FILE_COUNT,
            f"사진은 {REPEATABILITY_MIN_FILES}~{REPEATABILITY_MAX_FILES}장이어야 합니다: {len(files)}장",
            {
                "count": len(files),
                "min": REPEATABILITY_MIN_FILES,
                "max": REPEATABILITY_MAX_FILES,
            },
        )

    # 2) 판정 구간 로드 (시드가 없으면 여기서 바로 드러난다)
    try:
        category_lookup = _load_category_lookup(db)
    except skin_scoring.ScoringError as e:
        raise _error(400, e.code, str(e), e.detail) from e

    min_face_width = get_settings().min_face_width_px
    photos: list[RepeatabilityPhoto] = []
    rejected: list[RepeatabilityRejected] = []

    # 3) 사진마다 분석. 실패한 사진은 거절 목록에 넣고 계속 진행한다
    for upload in files:
        name = upload.filename or "(이름 없음)"
        if upload.content_type not in ALLOWED_CONTENT_TYPES:
            rejected.append(
                RepeatabilityRejected(
                    file=name,
                    code=ErrorCode.UNSUPPORTED_MEDIA_TYPE,
                    message=f"지원하지 않는 형식입니다: {upload.content_type}",
                )
            )
            continue
        try:
            scores, raw = skin_analysis.analyze_image_detail(
                upload.file.read(), min_face_width=min_face_width
            )
            categories = {
                code: skin_scoring.find_category(category_lookup[code], score).name
                for code, score in scores.items()
            }
        except (skin_analysis.AnalysisError, skin_scoring.ScoringError) as e:
            rejected.append(RepeatabilityRejected(file=name, code=e.code, message=str(e)))
            continue
        photos.append(
            RepeatabilityPhoto(file=name, scores=scores, categories=categories, raw=raw)
        )

    # 4) 통계를 내려면 성공한 사진이 2장 이상 있어야 한다
    if len(photos) < REPEATABILITY_MIN_FILES:
        raise _error(
            400,
            ErrorCode.INVALID_FILE_COUNT,
            f"분석에 성공한 사진이 {len(photos)}장뿐이라 통계를 낼 수 없습니다",
            {"rejected": [r.model_dump() for r in rejected]},
        )

    # 5) 지표별 통계
    metrics = [
        _summarize_metric(code, raw_key, judged_by, photos)
        for code, raw_key, judged_by in REPEATABILITY_METRICS
    ]

    # 6) 사진마다 분석에 쓰인 부위 (원시값에 "<부위>_l"이 있으면 사용된 부위)
    region_sets = {
        p.file: [r for r in REGION_NAMES if f"{r}_l" in p.raw] for p in photos
    }
    regions_consistent = len({tuple(v) for v in region_sets.values()}) == 1

    return RepeatabilityReport(
        photo_count=len(photos),
        rejected_count=len(rejected),
        metrics=metrics,
        regions_consistent=regions_consistent,
        region_sets=region_sets,
        photos=photos,
        rejected=rejected,
        criteria={
            "max_cv_percent": REPEATABILITY_MAX_CV,
            "max_score_range": REPEATABILITY_MAX_SCORE_RANGE,
        },
    )
