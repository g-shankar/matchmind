# PitchPulse: one image for the web app (API + built frontend) and the
# match simulator job. Build from the repo root:
#   docker build -f deployment/Dockerfile -t pitchpulse .

FROM node:20-slim AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

COPY backend/ ./backend/
RUN pip install "./backend[azure]" \
    && useradd --system --uid 10001 --home-dir /app --shell /usr/sbin/nologin pitchpulse
COPY --from=frontend /src/frontend/dist ./static

# The package is installed into site-packages, so point the API at the
# bundled demo match and the built frontend explicitly.
ENV MATCHMIND_MATCH_FILE=/app/backend/data/matches/MM-DEMO-001.jsonl \
    MATCHMIND_STATIC_DIR=/app/static

USER 10001
EXPOSE 8000
CMD ["uvicorn", "matchmind.api.app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
