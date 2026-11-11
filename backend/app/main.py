"""Application factory."""

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health
from app.api.v1 import (
    auth,
    availability,
    calendar_feeds,
    courses,
    insights,
    notifications,
    schedule,
    tasks,
    users,
)
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.core.rate_limit import AuthLimits


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(title="CoursePilot API", version="0.1.0")
    app.state.auth_limits = AuthLimits()
    register_error_handlers(app)

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    # Added last so it is outermost and sees every request and every failure.
    # HSTS only where the site is served over HTTPS, which production always is.
    app.add_middleware(RequestContextMiddleware, hsts=settings.environment == "production")

    api_v1 = APIRouter(prefix="/api/v1")
    api_v1.include_router(auth.router)
    api_v1.include_router(users.router)
    api_v1.include_router(courses.router)
    api_v1.include_router(tasks.router)
    api_v1.include_router(availability.router)
    api_v1.include_router(availability.preferences_router)
    api_v1.include_router(schedule.router)
    api_v1.include_router(schedule.sessions_router)
    api_v1.include_router(insights.router)
    api_v1.include_router(calendar_feeds.router)
    api_v1.include_router(calendar_feeds.suggestions_router)
    api_v1.include_router(calendar_feeds.busy_router)
    api_v1.include_router(notifications.router)
    app.include_router(api_v1)
    app.include_router(health.router)
    return app


app = create_app()
