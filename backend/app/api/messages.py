"""Mailbox message routes (authenticated)."""
import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.api.attachments import _get_service
from app.core.database import SessionLocal, get_db
from app.core.dependencies import get_current_mailbox, security
from app.core.events import broker
from app.models.mailbox import Mailbox, MailboxStatus
from app.schemas.message import MessageDetail, MessageReadUpdate, MessageSummary
from app.services.mailbox_service import MailboxService

router = APIRouter(prefix="/messages", tags=["messages"])

# How long an idle SSE connection waits before sending a keep-alive comment,
# so the proxy in front of uvicorn (and any load balancer beyond it) never
# sees a long silent stretch and times the connection out.
STREAM_KEEPALIVE_SECONDS = 20


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")


@router.get("", response_model=list[MessageSummary])
def list_messages(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    mailbox: Mailbox = Depends(get_current_mailbox),
    db: Session = Depends(get_db),
):
    return _get_service(db).list_for_mailbox(mailbox, limit, offset)


async def _mailbox_event_source(mailbox_id: int):
    """The SSE body for one mailbox: a module-level function (not a closure
    inside the route) so a test can drive it directly as a plain async
    generator, without going through a real HTTP connection — an in-process
    ASGI transport (TestClient or httpx.ASGITransport alike) only hands back
    a response after the generator finishes, which an endless stream never
    does.
    """
    queue = broker.subscribe(mailbox_id)
    try:
        yield "event: ready\ndata: {}\n\n"
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=STREAM_KEEPALIVE_SECONDS)
                yield f"event: {event}\ndata: {{}}\n\n"
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"
    finally:
        broker.unsubscribe(mailbox_id, queue)


@router.get("/stream")
async def stream_messages(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Server-Sent Events: pushes a nudge when new mail lands, instead of the
    client polling GET /messages on a timer.

    The database only has one connection in total (SQLite + StaticPool, see
    core/database.py), and this response can stay open for as long as a
    browser tab is, so — unlike every other route here — it must NOT depend
    on the request-scoped `get_db` session (that would hold the single
    connection hostage for the whole stream and freeze the rest of the app).
    The token is resolved with its own short-lived session instead, closed
    before the long-lived generator starts.
    """
    with SessionLocal() as db:
        session = MailboxService(db).get_session(credentials.credentials)
        if session is None or session.mailbox.status != MailboxStatus.ACTIVE:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session")
        mailbox_id = session.mailbox.id

    return StreamingResponse(
        _mailbox_event_source(mailbox_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Tells nginx specifically not to buffer this response, so each
            # event reaches the browser as soon as it is written rather than
            # waiting for a buffer to fill or the connection to close.
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{message_id}", response_model=MessageDetail)
def get_message(
    message_id: int,
    mailbox: Mailbox = Depends(get_current_mailbox),
    db: Session = Depends(get_db),
):
    message = _get_service(db).get_for_mailbox(mailbox, message_id)
    if message is None:
        raise _not_found()
    return message


@router.patch("/{message_id}/read", response_model=MessageSummary)
def update_read_state(
    message_id: int,
    payload: MessageReadUpdate,
    mailbox: Mailbox = Depends(get_current_mailbox),
    db: Session = Depends(get_db),
):
    service = _get_service(db)
    message = service.get_for_mailbox(mailbox, message_id)
    if message is None:
        raise _not_found()
    return service.set_read(message, payload.is_read)


@router.delete("/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_message(
    message_id: int,
    mailbox: Mailbox = Depends(get_current_mailbox),
    db: Session = Depends(get_db),
):
    service = _get_service(db)
    message = service.get_for_mailbox(mailbox, message_id)
    if message is None:
        raise _not_found()
    service.delete(message)
