from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import (
    actor,
    auth,
    cosmetics,
    dev,
    guest,
    hair,
    health,
    images,
    kiosk,
    me,
    qr,
    skin,
    terms,
)
from app.core.config import get_settings
from app.services import cleanup

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    # 매일 새벽 4시(KST) 만료 데이터 정리
    scheduler = BackgroundScheduler(timezone=cleanup.KST)
    job = scheduler.add_job(cleanup.run_cleanup, "cron", hour=cleanup.RUN_HOUR, id="cleanup_expired")
    scheduler.start()
    cleanup.logger.info("[정리] 다음 실행: %s", job.next_run_time)
    yield
    scheduler.shutdown(wait=False)


# 모든 API는 /api 아래에 둔다 (Vite 프록시, Vercel rewrites와 경로를 맞추기 위함)
app = FastAPI(
    title="BOA API", docs_url="/api/docs", openapi_url="/api/openapi.json", lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api = APIRouter(prefix="/api")
api.include_router(health.router)
api.include_router(images.router)
api.include_router(skin.router)
api.include_router(cosmetics.router)
api.include_router(hair.router)
api.include_router(actor.router)
api.include_router(terms.router)
api.include_router(guest.router)
api.include_router(auth.router)
api.include_router(qr.router)
api.include_router(kiosk.router)
api.include_router(me.router)
# 개발용 로그인은 DEV_LOGIN=true일 때만 노출한다
if settings.dev_login:
    api.include_router(dev.router)
app.include_router(api)

app.mount("/static", StaticFiles(directory="static"), name="static")
