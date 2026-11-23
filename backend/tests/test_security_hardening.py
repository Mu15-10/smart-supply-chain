import os

import pytest
from fastapi.testclient import TestClient
from redis.exceptions import RedisError

os.environ.setdefault("DATABASE_URL", "sqlite:///./test-security.db")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("JWT_SECRET", "test-secret-with-at-least-32-characters-long")
os.environ.setdefault("REGISTRATION_MAX_PER_IP", "5")

from app.core.config import Settings  # noqa: E402
from app.main import app, hit_limit, limiter_key, rds  # noqa: E402

client = TestClient(app)

try:
    REDIS_LIVE = rds is not None and bool(rds.ping())
except RedisError:
    REDIS_LIVE = False


def _registration_payload(index: int) -> dict:
    return {
        "email": f"limit-{index}@example.com",
        "password": "Madar!Secure2026",
        "display_name": f"Limit {index}",
        "tenant_code": f"limit-tenant-{index}",
        "tenant_name": f"Limit Tenant {index}",
    }


@pytest.mark.skipif(not REDIS_LIVE, reason="requires a reachable Redis service")
def test_registration_sixth_attempt_is_rate_limited():
    rds.flushdb()
    for index in range(5):
        response = client.post("/auth/register", json=_registration_payload(index))
        assert response.status_code == 201, response.text

    response = client.post("/auth/register", json=_registration_payload(5))
    assert response.status_code == 429
    assert response.headers["Retry-After"].isdigit()


@pytest.mark.skipif(not REDIS_LIVE, reason="requires a reachable Redis service")
def test_hit_limit_sets_ttl_in_same_transaction():
    rds.flushdb()
    key = limiter_key("test", "ttl-check")
    hit_limit(key, window=60)
    assert rds.ttl(key) > 0


def test_limiter_key_does_not_include_plain_email_or_ip():
    key = limiter_key("login-fail:acct", "person@example.com:203.0.113.10")
    assert "person@example.com" not in key
    assert "203.0.113.10" not in key
    assert key.startswith("login-fail:acct:")


def test_production_rejects_insecure_settings():
    settings = Settings(
        environment="production",
        jwt_secret="test-secret-with-at-least-32-characters-long",
        allowed_origins="https://app.example.com",
        docs_enabled=True,
    )
    with pytest.raises(ValueError, match="DOCS_ENABLED"):
        settings.validate_production()

    insecure_origins = Settings(
        environment="production",
        jwt_secret="test-secret-with-at-least-32-characters-long",
        allowed_origins="http://app.example.com",
        docs_enabled=False,
    )
    with pytest.raises(ValueError, match="HTTPS"):
        insecure_origins.validate_production()
