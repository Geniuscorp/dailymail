FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app

EXPOSE 8000

# One worker: SQLite has a single writer, and the in-process rate limiter is
# per process. Scale out only after moving both to a shared service.
#
# --forwarded-allow-ips='*': safe here only because this container publishes
# no port of its own (see docker-compose.yml) and is reachable exclusively
# from the `web` (nginx) container on the Compose network. Without this flag
# uvicorn's default (trust only 127.0.0.1) ignores nginx's X-Forwarded-For,
# so every request looks like it comes from the same internal IP and the
# per-client rate limiter in app/core/rate_limit.py becomes one shared budget
# for every real visitor.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
