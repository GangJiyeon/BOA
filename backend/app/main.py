from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import cosmetics, health, images, hair, skin
from app.core.config import get_settings

settings = get_settings()

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
api.include_router(cosmetics.router)
api.include_router(hair.router)
app.include_router(api)

app.mount("/static", StaticFiles(directory="static"), name="static")
