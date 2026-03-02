from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import admin, calls, chat, kb, marketing, messaging, rep, se, slack

api_router = APIRouter()
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(kb.router, prefix="/kb", tags=["kb"])
api_router.include_router(calls.router, prefix="/calls", tags=["calls"])
api_router.include_router(messaging.router, prefix="/messages", tags=["messages"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(rep.router, prefix="/rep", tags=["rep"])
api_router.include_router(se.router, prefix="/se", tags=["se"])
api_router.include_router(marketing.router, prefix="/marketing", tags=["marketing"])
api_router.include_router(slack.router, prefix="/slack", tags=["slack"])
