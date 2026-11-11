"""Environment-based configuration.

All settings come from environment variables (or a local ``.env`` file). Validating them at
startup makes a misconfigured deployment fail immediately instead of on the first request.
"""

from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_SECRET_MARKER = "dev-only"  # noqa: S105  # A marker to detect, not a credential.


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["local", "test", "production"] = "local"
    log_level: str = "INFO"

    database_url: str
    jwt_secret: SecretStr = Field(min_length=32)

    access_token_minutes: int = Field(default=15, gt=0)
    refresh_token_days: int = Field(default=30, gt=0)
    refresh_reuse_grace_seconds: int = Field(default=10, ge=0)
    cookie_secure: bool = True

    # Encrypts stored calendar links. Required in production; elsewhere the JWT secret is used.
    calendar_link_key: SecretStr | None = Field(default=None, min_length=32)

    # Empty by default: the frontend reaches the API on the same origin through a proxy.
    cors_origins: list[str] = []

    @model_validator(mode="after")
    def reject_unsafe_production_settings(self) -> Self:
        if self.environment != "production":
            return self
        if DEV_SECRET_MARKER in self.jwt_secret.get_secret_value():
            raise ValueError("JWT_SECRET must be replaced in production")
        if not self.cookie_secure:
            raise ValueError("COOKIE_SECURE must be true in production")
        if self.calendar_link_key is None:
            raise ValueError("CALENDAR_LINK_KEY must be set in production")
        if self.calendar_link_key.get_secret_value() == self.jwt_secret.get_secret_value():
            raise ValueError("CALENDAR_LINK_KEY must differ from JWT_SECRET")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # Required values come from the environment.
