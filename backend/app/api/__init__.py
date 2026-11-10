"""API routes."""
from fastapi import APIRouter
from app.api.mailbox import router as mailbox_router

api_router = APIRouter(prefix="/api")
api_router.include_router(mailbox_router)
