from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.api.deps import Actor, require_analysis_actor, require_owned_result
from app.services import quota
from app.db.session import get_db
from app.models.hair import (
    FaceAnalysis,
    HairRecommendation,
    HairRecRun,
    HairStyleCatalog,
    Sex,
)
from app.schemas.hair import (
    FaceAnalysisRequest,
    FaceAnalysisResult,
    HairRecommendRequest,
    HairRecommendResult,
    HairRecommendationItem,
    HairStyleRead,
)
from app.services.face_shape_analysis import analyze_face_shape
from app.services.hair_recommend import recommend_hairstyles
from app.services.landmark_extraction import extract_landmarks_from_bytes

MAX_PHOTO_BYTES = 10 * 1024 * 1024

router = APIRouter(prefix="/hair", tags=["hair"])


# ------------------------------------------------------------------
# 얼굴형 분석
# ------------------------------------------------------------------

@router.post("/face-analysis", status_code=201)
def create_face_analysis(body: FaceAnalysisRequest, actor: Actor = Depends(require_analysis_actor), db: Session = Depends(get_db)) -> FaceAnalysisResult:
    """사진 1장 또는 3장의 랜드마크를 받아 얼굴형을 분석하고 저장한다."""
    quota.check_quota(db, actor, "hair")
    landmark_sets = [
        {key: (point.x, point.y) for key, point in landmark_set.items()}
        for landmark_set in body.landmark_sets
    ]
    source = "single" if len(landmark_sets) == 1 else "triple"

    try:
        result = analyze_face_shape(landmark_sets, source=source)
    except ValueError as e:
        raise HTTPException(422, str(e))

    analysis = FaceAnalysis(
        user_id=actor.user_id,
        guest_id=actor.guest_id,
        image_id=body.image_id,
        sex=body.sex,
        face_shape=result["face_shape"],
        top2=result["top2"],
        confidence=result["confidence"],
        ratios=result["ratios"],
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)

    return FaceAnalysisResult(
        id=analysis.id,
        sex=analysis.sex,
        face_shape=analysis.face_shape,
        top2=analysis.top2,
        confidence=analysis.confidence,
        source=source,
        ratios=analysis.ratios,
        updated_at=analysis.updated_at,
    )


@router.post("/face-analysis/photos", status_code=201)
async def create_face_analysis_from_photos(
    photos: list[UploadFile] = File(..., description="1장(빠른 분석) 또는 3장(정밀 분석)"),
    sex: Sex = Form(..., description="사용자가 직접 선택한 성별"),
    actor: Actor = Depends(require_analysis_actor),
    image_id: int | None = Form(None),
    db: Session = Depends(get_db),
) -> FaceAnalysisResult:
    """
    사진 파일을 직접 받아 서버에서 MediaPipe로 좌표를 추출하고 얼굴형을 분석한다.
    프론트엔드가 좌표를 계산할 필요 없이 사진만 올리면 되는, 실제 서비스용 엔드포인트.
    (/face-analysis 는 좌표를 이미 가진 테스트/디버깅용으로 남겨둔다.)

    sex는 추천 시 헤어스타일 카탈로그를 성별로 필터링하는 데 쓰인다.
    (남자 얼굴에 여자 헤어스타일이 추천되는 것을 막기 위함)
    """
    quota.check_quota(db, actor, "hair")
    if not 1 <= len(photos) <= 3:
        raise HTTPException(422, "사진은 1장 또는 3장만 업로드할 수 있습니다.")

    landmark_sets = []
    for photo in photos:
        content = await photo.read(MAX_PHOTO_BYTES + 1)
        if len(content) > MAX_PHOTO_BYTES:
            raise HTTPException(413, "사진은 10MB 이하로 올려 주세요.")
        try:
            landmark_sets.append(extract_landmarks_from_bytes(content))
        except ValueError as e:
            raise HTTPException(422, f"'{photo.filename}' 처리 실패: {e}")

    source = "single" if len(landmark_sets) == 1 else "triple"

    try:
        result = analyze_face_shape(landmark_sets, source=source)
    except ValueError as e:
        raise HTTPException(422, str(e))

    analysis = FaceAnalysis(
        user_id=actor.user_id,
        guest_id=actor.guest_id,
        image_id=image_id,
        sex=sex,
        face_shape=result["face_shape"],
        top2=result["top2"],
        confidence=result["confidence"],
        ratios=result["ratios"],
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)

    return FaceAnalysisResult(
        id=analysis.id,
        sex=analysis.sex,
        face_shape=analysis.face_shape,
        top2=analysis.top2,
        confidence=analysis.confidence,
        source=source,
        ratios=analysis.ratios,
        updated_at=analysis.updated_at,
    )


@router.get("/face-analysis/{analysis_id}")
def get_face_analysis(analysis_id: int, actor: Actor = Depends(require_analysis_actor), db: Session = Depends(get_db)) -> FaceAnalysisResult:
    analysis = db.get(FaceAnalysis, analysis_id)
    require_owned_result(analysis, actor)
    if analysis is None:
        raise HTTPException(404, "얼굴형 분석 결과를 찾을 수 없습니다.")
    return FaceAnalysisResult(
        id=analysis.id,
        sex=analysis.sex,
        face_shape=analysis.face_shape,
        top2=analysis.top2,
        confidence=analysis.confidence,
        source="unknown",  # 저장 시점의 source는 별도로 남기지 않으므로 조회 시엔 알 수 없음
        ratios=analysis.ratios,
        updated_at=analysis.updated_at,
    )


# ------------------------------------------------------------------
# 헤어스타일 카탈로그
# ------------------------------------------------------------------

@router.get("/styles")
def list_styles(db: Session = Depends(get_db)) -> list[HairStyleRead]:
    # DB의 물리적 행 순서는 수정 후 바뀔 수 있으므로 카탈로그 번호로 고정한다.
    styles = db.scalars(select(HairStyleCatalog).order_by(
        case((HairStyleCatalog.sex == Sex.MALE, 0), (HairStyleCatalog.sex == Sex.FEMALE, 1), else_=2),
        HairStyleCatalog.style_id,
    )).all()
    return [HairStyleRead.model_validate(s, from_attributes=True) for s in styles]


# ------------------------------------------------------------------
# 추천 실행
# ------------------------------------------------------------------

@router.post("/recommend", status_code=201)
def create_recommendation(body: HairRecommendRequest, actor: Actor = Depends(require_analysis_actor), db: Session = Depends(get_db)) -> HairRecommendResult:
    """얼굴형 분석 결과 + 선호 조건으로 헤어스타일을 추천하고 결과를 저장한다."""
    face_analysis = db.get(FaceAnalysis, body.face_analysis_id)
    require_owned_result(face_analysis, actor)
    quota.check_quota(db, actor, "hair")
    if face_analysis is None:
        raise HTTPException(404, "참조한 얼굴형 분석 결과를 찾을 수 없습니다.")

    # face_analysis.sex와 같은 성별이거나 unisex인 스타일만 후보로 삼는다.
    styles = db.scalars(
        select(HairStyleCatalog).where(
            HairStyleCatalog.sex.in_([face_analysis.sex, Sex.UNISEX])
        )
    ).all()
    style_dicts = [
        {
            "style_id": s.style_id,
            "name": s.name,
            "length": s.length,
            "texture": s.texture,
            "face_fit": s.face_fit,
            "asset_id": s.asset_id,
            "image": s.image,
            "guide": s.guide,
        }
        for s in styles
    ]

    results = recommend_hairstyles(
        face_shape=face_analysis.face_shape,
        style_candidates=style_dicts,
        texture_pref=body.preferred_texture,
        length_pref=body.preferred_length,
        top_n=body.top_n,
        weights=body.weights,
    )

    run = HairRecRun(
        user_id=actor.user_id,
        guest_id=actor.guest_id,
        face_analysis_id=body.face_analysis_id,
        preferred_length=body.preferred_length,
        preferred_texture=body.preferred_texture,
        weights=body.weights,
        top_n=body.top_n,
    )
    db.add(run)
    db.flush()  # run.id 를 미리 확보하기 위해 커밋 전에 flush

    for rank, r in enumerate(results, start=1):
        db.add(HairRecommendation(
            run_id=run.id,
            rank=rank,
            style_id=r["style_id"],
            face_fit=r["face_fit"],
            texture_fit=r["texture_fit"],
            length_fit=r["length_fit"],
            score=r["score"],
        ))
    db.commit()

    return HairRecommendResult(
        run_id=run.id,
        face_analysis_id=body.face_analysis_id,
        preferred_length=body.preferred_length,
        preferred_texture=body.preferred_texture,
        created_at=run.created_at,
        recommendations=[
            HairRecommendationItem(rank=i, **r) for i, r in enumerate(results, start=1)
        ],
    )


@router.get("/recommend/{run_id}")
def get_recommendation(run_id: int, actor: Actor = Depends(require_analysis_actor), db: Session = Depends(get_db)) -> HairRecommendResult:
    """특정 run의 추천 결과 + 그 당시 조건을 복원한다."""
    run = db.get(HairRecRun, run_id)
    require_owned_result(run, actor)
    if run is None:
        raise HTTPException(404, "추천 이력을 찾을 수 없습니다.")

    recs = db.scalars(
        select(HairRecommendation)
        .where(HairRecommendation.run_id == run_id)
        .order_by(HairRecommendation.rank)
    ).all()

    style_map = {
        s.style_id: s for s in db.scalars(select(HairStyleCatalog)).all()
    }

    return HairRecommendResult(
        run_id=run.id,
        face_analysis_id=run.face_analysis_id,
        preferred_length=run.preferred_length,
        preferred_texture=run.preferred_texture,
        created_at=run.created_at,
        recommendations=[
            HairRecommendationItem(
                rank=rec.rank,
                style_id=rec.style_id,
                name=style_map[rec.style_id].name if rec.style_id in style_map else "",
                face_fit=rec.face_fit,
                texture_fit=rec.texture_fit,
                length_fit=rec.length_fit,
                score=rec.score,
                note=style_map[rec.style_id].guide if rec.style_id in style_map else None,
                asset_id=style_map[rec.style_id].asset_id if rec.style_id in style_map else None,
                image=style_map[rec.style_id].image if rec.style_id in style_map else None,
            )
            for rec in recs
        ],
    )
