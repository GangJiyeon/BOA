from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    actor,
    auth,
    dev,
    guest,
    health,
    images,
    kiosk,
    me,
    qr,
    skin,
    terms,
)
from app.core.config import get_settings

settings = get_settings()

# 모든 API는 /api 아래에 둔다 (Vite 프록시, Vercel rewrites와 경로를 맞추기 위함)
app = FastAPI(title="BOA API", docs_url="/api/docs", openapi_url="/api/openapi.json")

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
