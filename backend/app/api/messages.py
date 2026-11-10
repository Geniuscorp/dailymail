"""Mailbox message routes (authenticated)."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_mailbox
from app.models.mailbox import Mailbox
from app.schemas.message import MessageDetail, MessageReadUpdate, MessageSummary
from app.services.message_service import MessageService

router = APIRouter(prefix="/messages", tags=["messages"])


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")


@router.get("", response_model=list[MessageSummary])
def list_messages(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    mailbox: Mailbox = Depends(get_current_mailbox),
    db: Session = Depends(get_db),
):
    return MessageService(db).list_for_mailbox(mailbox, limit, offset)


@router.get("/{message_id}", response_model=MessageDetail)
def get_message(
    message_id: int,
    mailbox: Mailbox = Depends(get_current_mailbox),
    db: Session = Depends(get_db),
):
    message = MessageService(db).get_for_mailbox(mailbox, message_id)
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
    service = MessageService(db)
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
    service = MessageService(db)
    message = service.get_for_mailbox(mailbox, message_id)
    if message is None:
        raise _not_found()
    service.delete(message)
