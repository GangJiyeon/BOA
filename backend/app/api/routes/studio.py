from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import Actor, get_actor, require_analysis_actor
from app.core.config import get_settings
from app.db.session import get_db
from app.models import HairRecRun, HairRender, HairStyleCatalog
from app.schemas.studio import HairRenderBase, HairRenderRead
from app.services import hair_studio, quota

router = APIRouter(prefix="/studio", tags=["studio"])

MAX_PHOTO_BYTES = 10 * 1024 * 1024


def _read(render: HairRender) -> HairRenderRead:
    done = render.status == "done"

    def base(name: str) -> HairRenderBase | None:
        if not done:
            return None
        return HairRenderBase(
            image=hair_studio.asset_url(render.asset_dir, f"{name}.jpg"),
            mask=hair_studio.asset_url(render.asset_dir, f"{name}_mask.png"),
        )

    return HairRenderRead(
        id=render.id,
        style_id=render.style_id,
        status=render.status,
        error=render.error,
        created_at=render.created_at,
        light=base("light"),
        mid=base("mid"),
    )


@router.post("/hair-renders", status_code=202)
async def create_hair_render(
    background: BackgroundTasks,
    photo: UploadFile = File(..., description="정면 얼굴 사진 1장 (JPG/PNG/WEBP)"),
    style_id: str = Form(...),
    run_id: int | None = Form(None, description="추천 결과에서 고른 경우 그 run id"),
    actor: Actor = Depends(require_analysis_actor),
    db: Session = Depends(get_db),
) -> HairRenderRead:
    """추천 스타일을 사진에 합성 (약 20~30초, GET으로 상태 확인)

    원본 사진은 저장 안 하고 합성에만 사용
    """
    if not get_settings().gemini_api_key:
        raise HTTPException(503, "AI 스튜디오가 설정되지 않았습니다")
    style = db.get(HairStyleCatalog, style_id)
    if style is None:
        raise HTTPException(404, "헤어스타일을 찾을 수 없습니다")
    if run_id is not None and db.get(HairRecRun, run_id) is None:
        raise HTTPException(404, "추천 이력을 찾을 수 없습니다")
    quota.check_quota(db, actor, "studio")

    data = await photo.read()
    if len(data) > MAX_PHOTO_BYTES:
        raise HTTPException(413, "사진은 10MB 이하로 올려 주세요")
    # 얼굴 없는 사진은 AI 호출(유료) 전에 거절
    try:
        hair_studio.landmarks(hair_studio.decode_image(data))
    except ValueError as e:
        raise HTTPException(422, str(e))

    render = HairRender(
        user_id=actor.user_id,
        guest_id=actor.guest_id if actor.kind != "member" else None,
        run_id=run_id,
        style_id=style_id,
        asset_dir=hair_studio.new_asset_dir(),
    )
    db.add(render)
    db.commit()
    db.refresh(render)
    background.add_task(hair_studio.process_render, render.id, data)
    return _read(render)


@router.get("/hair-renders/{render_id}")
def read_hair_render(
    render_id: int, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)
) -> HairRenderRead:
    """본인(회원 또는 같은 비회원 세션) 결과만 조회"""
    render = db.get(HairRender, render_id)
    mine = render is not None and (
        (actor.user_id is not None and render.user_id == actor.user_id)
        or (actor.guest_id is not None and render.guest_id == actor.guest_id)
    )
    if not mine:
        raise HTTPException(404, "합성 결과를 찾을 수 없습니다")
    return _read(render)
