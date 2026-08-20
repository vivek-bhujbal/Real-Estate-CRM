from fastapi import APIRouter

from app.api.v1 import auth, dashboard

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(dashboard.router)
