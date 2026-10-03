# PetPulse demo image: starts with zero secrets (fake AI providers, local JSON store).
#   docker compose up                                  # demo
#   INSTALL_LIVE=true docker compose build             # adds optional Google STT + Firebase deps (requirements/live.txt)
FROM python:3.11-slim

ARG INSTALL_LIVE=false

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DATA_DIR=/app/data

WORKDIR /app

# Pinned, wheel-only dependencies: no compilers, no portaudio.
COPY requirements/base.txt requirements/live.txt requirements/
RUN pip install --only-binary=:all: -r requirements/base.txt \
    && if [ "$INSTALL_LIVE" = "true" ]; then pip install --only-binary=:all: -r requirements/live.txt -c requirements/base.txt; fi

# Non-root user. Code stays root-owned (read-only for the app); only data/ is writable.
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin app \
    && mkdir -p /app/data \
    && chown app:app /app/data

COPY --chown=root:root . .

USER app

EXPOSE 8000

# curl is not in the slim image; use Python.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3).status == 200 else 1)"]

CMD ["uvicorn", "petpulse.app:app", "--host", "0.0.0.0", "--port", "8000"]
