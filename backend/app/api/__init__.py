"""API routes."""
from fastapi import APIRouter
from app.api.admin import router as admin_router
from app.api.attachments import router as attachments_router
from app.api.mailbox import router as mailbox_router
from app.api.messages import router as messages_router
from app.api.webhooks import router as webhooks_router

api_router = APIRouter(prefix="/api")
api_router.include_router(mailbox_router)
api_router.include_router(messages_router)
api_router.include_router(attachments_router)
api_router.include_router(webhooks_router)
api_router.include_router(admin_router)
