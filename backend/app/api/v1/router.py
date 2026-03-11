from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.health import router as health_router
from app.api.v1.resources import router as resources_router
from app.api.v1.ingest import router as ingest_router
from app.api.v1.sessions import router as sessions_router
from app.api.v1.tutor import router as tutor_router
from app.api.v1.users import router as users_router
from app.api.v1.billing import router as billing_router
from app.api.v1.quiz import router as quiz_router
from app.api.v1.notebooks import router as notebooks_router
from app.api.v1.models_api import router as models_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(health_router)
api_router.include_router(resources_router)
api_router.include_router(ingest_router)
api_router.include_router(sessions_router)
api_router.include_router(tutor_router)
api_router.include_router(users_router)
api_router.include_router(billing_router)
api_router.include_router(quiz_router)
api_router.include_router(notebooks_router)
api_router.include_router(models_router)
