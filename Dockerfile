# Production image: the API and the built web app in one container, on one origin.
# Local development uses docker-compose.yml and the Dockerfiles in backend/ and frontend/.

# --- Build the web app ---
FROM node:26-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-fund --no-audit
COPY frontend/ ./
RUN npm run build

# --- Run the API, which also serves the built pages ---
FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    ENVIRONMENT=production \
    STATIC_DIR=/app/static
WORKDIR /app

# Dependencies first, from placeholder packages, so that a code change reuses this layer.
COPY backend/pyproject.toml ./
RUN mkdir app scheduler \
    && touch app/__init__.py scheduler/__init__.py \
    && pip install . \
    && pip uninstall -y coursepilot-backend

COPY backend/app ./app
COPY backend/scheduler ./scheduler
COPY backend/migrations ./migrations
COPY backend/alembic.ini ./
COPY --from=web /web/dist ./static

RUN useradd --create-home appuser
USER appuser

# The hosting platform sets PORT. Migrations run first: the free plan has no separate release
# step. Only one instance runs on that plan, so two never migrate at once.
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --no-access-log"]
