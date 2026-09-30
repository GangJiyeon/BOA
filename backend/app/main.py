from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import health, images, skin
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
app.include_router(api)
