"""피부 분석 API.

흐름: (프론트) S3 업로드 → POST /api/images 로 image_id 확보
      → 로컬 브릿지에서 수분값 수신 → 여기로 한 번에 POST
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Image, SkinAnalysis
from app.schemas.skin import AnalysisCreate, AnalysisRead, ScoreRead
from app.services import skin_analysis, skin_scoring

router = APIRouter(prefix="/skin", tags=["skin"])


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


@router.post("/analyses", status_code=201)
def create_analysis(body: AnalysisCreate, db: Session = Depends(get_db)) -> AnalysisRead:
    """사진과 수분값으로 분석 1건을 만든다.

    점수 산출 → 구간 판정 → 저장까지 한 요청에서 끝낸다(동기 처리).
    """
    image = None
    if body.image_id is not None:
        image = db.get(Image, body.image_id)
        if image is None:
            raise HTTPException(404, f"이미지를 찾을 수 없습니다: {body.image_id}")

    try:
        # TODO(CV): 실제 분석 구현 후에는 S3에서 원본을 받아 image_bytes로 넘긴다.
        scores = skin_analysis.build_scores(
            seed_key=image.s3_key if image else str(body.guest_id or body.image_id or "dev"),
            moisture_source=body.moisture_source,
            moisture_raw=body.moisture_raw,
            moisture_score=body.moisture_score,
        )
        analysis = skin_scoring.label_and_save(
            db,
            scores=scores,
            moisture_source=body.moisture_source,
            guest_id=body.guest_id,
            image_id=body.image_id,
        )
    except (skin_analysis.AnalysisError, skin_scoring.ScoringError) as e:
        raise HTTPException(400, str(e)) from e

    db.commit()
    db.refresh(analysis)
    return to_read(analysis)


@router.get("/analyses/{analysis_id}")
def get_analysis(analysis_id: int, db: Session = Depends(get_db)) -> AnalysisRead:
    analysis = db.scalar(select(SkinAnalysis).where(SkinAnalysis.id == analysis_id))
    if analysis is None:
        raise HTTPException(404, f"분석 결과를 찾을 수 없습니다: {analysis_id}")
    return to_read(analysis)
