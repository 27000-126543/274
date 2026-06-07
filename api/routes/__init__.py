from fastapi import APIRouter
from . import auth, cases, ips, system

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(cases.router)
api_router.include_router(ips.router)
api_router.include_router(system.router)

__all__ = ["api_router"]
