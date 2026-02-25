from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import admin, calls, chat, kb, messaging

api_router = APIRouter()
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(kb.router, prefix="/kb", tags=["kb"])
api_router.include_router(calls.router, prefix="/calls", tags=["calls"])
api_router.include_router(messaging.router, prefix="/messages", tags=["messages"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
