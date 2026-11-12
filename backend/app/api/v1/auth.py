"""Authentication endpoints."""

from typing import Annotated

from fastapi import APIRouter, Cookie, Request, Response, status

from app.api.deps import AppSettings, DbSession
from app.core.config import Settings
from app.core.errors import InvalidCredentialsError
from app.core.rate_limit import AuthLimits
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


def _limits(request: Request) -> AuthLimits:
    limits: AuthLimits = request.app.state.auth_limits
    return limits


def _address(request: Request, settings: Settings) -> str:
    """The visitor's address, for rate limits only.

    Behind a hosting platform's proxy the peer is the proxy, so production names the header its
    edge sets (see ``client_ip_header``). That header is set by the edge, not the visitor.
    """
    if settings.client_ip_header:
        supplied = request.headers.get(settings.client_ip_header, "").strip()
        if supplied:
            return supplied[:64]
    return request.client.host if request.client else "unknown"


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(
    data: RegisterRequest,
    request: Request,
    response: Response,
    db: DbSession,
    settings: AppSettings,
) -> AuthResponse:
    limit, address = _limits(request).register_per_address, _address(request, settings)
    limit.check(address)
    tokens = auth_service.register(db, data, settings)
    limit.record(address)
    return _auth_response(response, tokens, settings)


@router.post("/login")
def login(
    data: LoginRequest,
    request: Request,
    response: Response,
    db: DbSession,
    settings: AppSettings,
) -> AuthResponse:
    limits, address = _limits(request), _address(request, settings)
    account = f"{address}|{data.email.strip().lower()}"
    limits.login_per_account.check(account)
    limits.login_per_address.check(address)
    try:
        tokens = auth_service.login(db, data.email, data.password, settings)
    except InvalidCredentialsError:
        limits.login_per_account.record(account)
        limits.login_per_address.record(address)
        raise
    limits.login_per_account.clear(account)
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
