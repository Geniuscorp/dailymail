"""FastAPI dependencies."""
import hmac

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import decode_admin_token
from app.models.admin_user import AdminUser, AdminUserStatus
from app.models.mailbox import Mailbox, MailboxStatus
from app.models.mailbox_session import MailboxSession
from app.services.mailbox_service import MailboxService

security = HTTPBearer()
admin_security = HTTPBearer()

CREATION_SECRET_HEADER = "x-dailymail-creation-secret"


def require_creation_secret(request: Request) -> None:
    """Gate mailbox creation behind the shared secret when one is configured."""
    expected = get_settings().mailbox_creation_secret
    if not expected:
        return

    provided = request.headers.get(CREATION_SECRET_HEADER, "")
    if not hmac.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Mailbox creation is not allowed",
        )


def get_current_mailbox_session(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> MailboxSession:
    """Resolve the bearer token to a live, persistent mailbox session.

    The token is opaque and looked up in the database (not decoded like a
    JWT), which is what lets a session be revoked on logout or password
    change instead of only expiring on its own schedule.
    """
    service = MailboxService(db)
    session = service.get_session(credentials.credentials)

    if session is None or session.mailbox.status != MailboxStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        )

    return session


def get_current_mailbox(
    session: MailboxSession = Depends(get_current_mailbox_session),
) -> Mailbox:
    """Get the mailbox behind the current session."""
    return session.mailbox


def get_current_admin(
    credentials: HTTPAuthorizationCredentials = Depends(admin_security),
    db: Session = Depends(get_db),
) -> AdminUser:
    """Get the authenticated admin user behind an admin-scoped token."""
    username = decode_admin_token(credentials.credentials)
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired admin token",
        )

    admin = (
        db.query(AdminUser)
        .filter(
            AdminUser.username == username,
            AdminUser.status == AdminUserStatus.ACTIVE,
        )
        .first()
    )
    if admin is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin user not found",
        )
    return admin
