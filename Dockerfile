# syntax=docker/dockerfile:1
# Single-origin image: the React app is built in stage 1 and served by FastAPI in stage 2,
# so the browser talks to one host for HTML, REST and WebSocket.

# ---- stage 1: build the frontend -------------------------------------------------------
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- stage 2: Python runtime -----------------------------------------------------------
FROM python:3.12-slim AS app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    STATIC_DIR=/app/static \
    MAX_SESSIONS=2 \
    PORT=8000
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install -r requirements.txt
COPY backend/trafficsim ./trafficsim
COPY --from=web /web/dist ./static
RUN useradd --create-home --uid 10001 app
USER app
EXPOSE 8000
# One worker on purpose: live sessions and the session cap are held in this process.
CMD ["sh", "-c", "exec uvicorn trafficsim.server.app:app --host 0.0.0.0 --port ${PORT} --workers 1 --proxy-headers --forwarded-allow-ips '*'"]
