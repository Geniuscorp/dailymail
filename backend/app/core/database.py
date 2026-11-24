"""Database configuration and session management."""
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings

settings = get_settings()

# How long a connection waits for SQLite's single write lock before giving up.
_SQLITE_BUSY_TIMEOUT_SECONDS = 30


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def _is_in_memory_sqlite(url: str) -> bool:
    return _is_sqlite(url) and (url in ("sqlite://", "sqlite:///") or ":memory:" in url)


def build_engine(database_url: str) -> Engine:
    """Create the engine, giving every request its own connection.

    FastAPI runs the sync routes on a thread pool, so requests overlap. The
    engine used to be pinned to ONE shared connection (``StaticPool``): two
    threads then drove the same SQLite cursor/transaction at once, and the
    result was silently wrong data (a query returning no row for something that
    exists, short result lists, ``IndexError`` out of the driver) and one
    request's rollback undoing another's in-flight write. Under real traffic
    that looked like random logouts, empty inboxes and failed downloads with
    no error to point at. A normal pool hands each session its own connection.

    An in-memory SQLite database is the one case that still needs a single
    shared connection (each new connection would otherwise be its own empty
    database), so it keeps ``StaticPool``; that is a test-only setup.
    """
    if not _is_sqlite(database_url):
        return create_engine(database_url, pool_pre_ping=True)

    if _is_in_memory_sqlite(database_url):
        return create_engine(
            database_url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

    new_engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False, "timeout": _SQLITE_BUSY_TIMEOUT_SECONDS},
    )

    @event.listens_for(new_engine, "connect")
    def _tune_connection(dbapi_connection, _record) -> None:
        cursor = dbapi_connection.cursor()
        try:
            # WAL lets readers run while one writer commits; with the default
            # rollback journal every read would block behind a write.
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
        except Exception:
            # Some filesystems cannot do WAL; the default journal still works.
            pass
        finally:
            cursor.close()

    return new_engine


engine = build_engine(settings.database_url)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """Dependency for getting database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
