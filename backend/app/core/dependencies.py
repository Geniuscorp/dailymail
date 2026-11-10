"""FastAPI dependencies."""
import hmac

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import decode_access_token, decode_admin_token
from app.models.admin_user import AdminUser, AdminUserStatus
from app.models.mailbox import Mailbox
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


def get_current_mailbox(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> Mailbox:
    """Get current authenticated mailbox."""
    token = credentials.credentials
    email = decode_access_token(token)

    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    service = MailboxService(db)
    mailbox = service.get_mailbox(email)

    if not mailbox:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Mailbox not found",
        )

    return mailbox


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
