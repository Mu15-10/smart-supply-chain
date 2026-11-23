"""Central environment validation for the foundation gate."""

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        case_sensitive=False,
    )

    service: str = "all"
    environment: str = "development"
    database_url: str = "sqlite:///./supply.db"
    jwt_secret: str = Field(default="", min_length=32)
    redis_url: str = "redis://localhost:6379/0"
    mongo_url: str = "mongodb://localhost:27017"
    allowed_origins: str = "http://localhost:5173"
    allowed_hosts: str = "localhost,127.0.0.1"
    docs_enabled: bool = True
    log_level: str = "INFO"
    trusted_proxy_count: int = Field(default=0, ge=0)
    login_max_per_ip: int = Field(default=20, gt=0)
    login_max_per_account_ip: int = Field(default=5, gt=0)
    login_window_seconds: int = Field(default=900, gt=0)
    registration_max_per_ip: int = Field(default=5, gt=0)
    refresh_max_per_ip: int = Field(default=30, gt=0)
    refresh_window_seconds: int = Field(default=60, gt=0)
    access_token_minutes: int = Field(default=15, gt=0)
    refresh_token_days: int = Field(default=7, gt=0)
    allow_public_registration: bool | None = None
    return_invitation_token: bool | None = None

    @field_validator("environment")
    @classmethod
    def known_environment(cls, value: str) -> str:
        if value not in {"development", "test", "staging", "production"}:
            raise ValueError("ENVIRONMENT must be development, test, staging, or production")
        return value

    def model_post_init(self, __context: object, /) -> None:
        if self.allow_public_registration is None:
            self.allow_public_registration = self.environment != "production"
        if self.return_invitation_token is None:
            self.return_invitation_token = self.environment != "production"

    def validate_production(self) -> None:
        origins = [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]
        if self.environment == "production" and (
            not origins or "*" in origins or any(origin.startswith("http://") for origin in origins)
        ):
            raise ValueError("Production ALLOWED_ORIGINS must contain explicit HTTPS origins")
        if self.environment == "production" and self.docs_enabled:
            raise ValueError("DOCS_ENABLED must be false in production")
        if self.environment == "production" and self.allow_public_registration:
            raise ValueError("ALLOW_PUBLIC_REGISTRATION must be false in production")
        if self.environment == "production" and self.return_invitation_token:
            raise ValueError("RETURN_INVITATION_TOKEN must be false in production")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_production()
    return settings
