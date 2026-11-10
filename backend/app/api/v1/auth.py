"""Authentication endpoints."""

from typing import Annotated

from fastapi import APIRouter, Cookie, Response, status

from app.api.deps import AppSettings, DbSession
from app.core.config import Settings
from app.schemas.auth import AuthResponse, LoginRequest, RegisterRequest, UserRead
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "coursepilot_refresh"
# The browser sends the cookie only to authentication endpoints, never to the rest of the API.
REFRESH_COOKIE_PATH = "/api/v1/auth"

RefreshCookie = Annotated[str | None, Cookie(alias=REFRESH_COOKIE)]


def _auth_response(
    response: Response, tokens: auth_service.IssuedTokens, settings: Settings
) -> AuthResponse:
    response.set_cookie(
        REFRESH_COOKIE,
        tokens.refresh_token,
        max_age=settings.refresh_token_days * 86_400,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
    )
    return AuthResponse(
        access_token=tokens.access_token,
        expires_in=settings.access_token_minutes * 60,
        user=UserRead.model_validate(tokens.user),
    )


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(
    data: RegisterRequest, response: Response, db: DbSession, settings: AppSettings
) -> AuthResponse:
    return _auth_response(response, auth_service.register(db, data, settings), settings)


@router.post("/login")
def login(
    data: LoginRequest, response: Response, db: DbSession, settings: AppSettings
) -> AuthResponse:
    tokens = auth_service.login(db, data.email, data.password, settings)
    return _auth_response(response, tokens, settings)


@router.post("/refresh")
def refresh(
    response: Response, db: DbSession, settings: AppSettings, token: RefreshCookie = None
) -> AuthResponse:
    return _auth_response(response, auth_service.refresh(db, token, settings), settings)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response, db: DbSession, token: RefreshCookie = None) -> None:
    auth_service.logout(db, token)
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_COOKIE_PATH)
