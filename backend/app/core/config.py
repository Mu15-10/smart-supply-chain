"""Central environment validation for the foundation gate."""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore', case_sensitive=False)
    environment: str = 'development'
    jwt_secret: str = Field(min_length=32)
    allowed_origins: str = 'http://localhost:5173'
    allowed_hosts: str = 'localhost,127.0.0.1'
    docs_enabled: bool = True

    @field_validator('environment')
    @classmethod
    def known_environment(cls, value: str) -> str:
        if value not in {'development', 'test', 'staging', 'production'}:
            raise ValueError('ENVIRONMENT must be development, test, staging, or production')
        return value

    def validate_production(self) -> None:
        origins = [origin.strip() for origin in self.allowed_origins.split(',') if origin.strip()]
        if self.environment == 'production' and (not origins or '*' in origins or any(origin.startswith('http://') and 'localhost' not in origin for origin in origins)):
            raise ValueError('Production ALLOWED_ORIGINS must contain explicit HTTPS origins')
        if self.environment == 'production' and self.docs_enabled:
            raise ValueError('DOCS_ENABLED must be false in production')

@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_production()
    return settings
