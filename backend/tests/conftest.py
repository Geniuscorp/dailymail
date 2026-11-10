"""Shared test configuration: isolated in-memory database and fixed secrets."""
import os

os.environ.setdefault("INBOUND_EMAIL_PROVIDER", "cloudflare_worker")
os.environ.setdefault("INBOUND_WEBHOOK_SECRET", "test-webhook-secret")
os.environ.setdefault("ACCESS_TOKEN_SECRET", "test-access-secret")
# Suites create many mailboxes from the same client; the limiter has its own tests.
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.database import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402

get_settings.cache_clear()

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
