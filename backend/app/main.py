"""FastAPI application initialization."""
import asyncio
import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import get_settings
from app.api import api_router
from app.storage.base import StorageError
from app.tasks.retention import run_sweep_once

settings = get_settings()

# The app's own loggers had no handler, so every logger.info/warning in the
# service (e.g. why an inbound message was dropped) was silently swallowed and
# only uvicorn's access log showed. Attach one handler to the "app" namespace,
# at INFO, writing to stdout (where the platform collects logs). Scoped to
# "app" and with propagate off, so it neither duplicates uvicorn's access log
# nor depends on root logging config.
_app_logger = logging.getLogger("app")
if not _app_logger.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
    _app_logger.addHandler(_handler)
    _app_logger.setLevel(logging.INFO)
    _app_logger.propagate = False

logger = logging.getLogger(__name__)

# Short enough that a sweep still runs soon after a container restarts (so
# retention isn't silently skipped on a platform that restarts often), long
# enough to not race the app's own startup.
_RETENTION_FIRST_RUN_DELAY_SECONDS = 60


async def _retention_loop() -> None:
    """Runs the retention sweep on a timer for the life of this process.

    Lives here, not as a separate scheduled job/container, so it works
    identically on any deployment target without platform-specific setup
    (no shared volume or cron needed) — see docs/ARCHITECTURE.md.
    """
    await asyncio.sleep(_RETENTION_FIRST_RUN_DELAY_SECONDS)
    while True:
        try:
            purged = await asyncio.to_thread(run_sweep_once)
            if purged:
                logger.info("retention sweep removed %s expired message(s)", purged)
        except StorageError as exc:
            logger.error("retention sweep skipped: %s", exc)
        except Exception:
            logger.exception("retention sweep failed unexpectedly")
        await asyncio.sleep(settings.retention_sweep_interval_hours * 3600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = None
    if settings.retention_sweep_enabled:
        task = asyncio.create_task(_retention_loop())
    yield
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title=settings.app_name,
    description="Private temporary email service",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "environment": settings.environment}
