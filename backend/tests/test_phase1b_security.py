from __future__ import annotations

from contextlib import contextmanager

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

import app.main as main
from app.main import RefreshIn, app

client = TestClient(app)


def _request(headers: dict[str, str] | None = None, client_host: str = "10.0.0.10") -> Request:
    raw_headers = [(key.lower().encode(), value.encode()) for key, value in (headers or {}).items()]
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": raw_headers,
        "client": (client_host, 1234),
        "server": ("testserver", 80),
    }
    return Request(scope)


@contextmanager
def _patched_refresh_limiter(monkeypatch: pytest.MonkeyPatch):
    calls: list[tuple[str, int]] = []

    def capture_check(key: str, limit: int) -> None:
        calls.append((key, limit))

    def capture_hit(key: str, window: int) -> None:
        calls.append((key, window))

    monkeypatch.setattr(main, "check_limit", capture_check)
    monkeypatch.setattr(main, "hit_limit", capture_hit)
    original_max = main.settings.refresh_max_per_ip
    original_window = main.settings.refresh_window_seconds
    main.settings.refresh_max_per_ip = 7
    main.settings.refresh_window_seconds = 11
    try:
        yield calls
    finally:
        main.settings.refresh_max_per_ip = original_max
        main.settings.refresh_window_seconds = original_window


def test_refresh_limiter_uses_hashed_ip_and_configured_limits(monkeypatch: pytest.MonkeyPatch):
    with _patched_refresh_limiter(monkeypatch) as calls:
        with pytest.raises(HTTPException) as raised:
            main.refresh(_request(client_host="10.0.0.20"), RefreshIn(refresh_token="x" * 20))

    assert raised.value.status_code == 401
    assert len(calls) == 2
    assert calls[0][1] == 7
    assert calls[1][1] == 11
    assert all("10.0.0.20" not in key for key, _ in calls)
    assert all(key.startswith("refresh:") for key, _ in calls)


def test_trusted_proxy_uses_first_untrusted_forwarded_address(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(main, "TRUSTED_PROXY_COUNT", 1)
    request = _request({"X-Forwarded-For": "198.51.100.8, 10.0.0.1"}, client_host="10.0.0.1")

    assert main.get_client_ip(request) == "198.51.100.8"


def test_forwarded_address_is_ignored_without_trusted_proxy(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(main, "TRUSTED_PROXY_COUNT", 0)
    request = _request({"X-Forwarded-For": "198.51.100.8"}, client_host="10.0.0.1")

    assert main.get_client_ip(request) == "10.0.0.1"


class _BrokenRedis:
    def ping(self):
        raise main.RedisError("redis unavailable")

    def pipeline(self, transaction: bool = True):
        raise main.RedisError("redis unavailable")


def test_redis_availability_fails_closed_in_production(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(main, "rds", _BrokenRedis())
    monkeypatch.setattr(main, "ENVIRONMENT", "production")

    with pytest.raises(HTTPException, match="AUTH_TEMPORARILY_UNAVAILABLE") as raised:
        main.redis_available()

    assert raised.value.status_code == 503


def test_redis_limiter_write_fails_closed_in_production(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(main, "rds", _BrokenRedis())
    monkeypatch.setattr(main, "ENVIRONMENT", "production")

    with pytest.raises(HTTPException, match="AUTH_TEMPORARILY_UNAVAILABLE") as raised:
        main.hit_limit("phase1b-fail-closed", window=60)

    assert raised.value.status_code == 503


def test_cors_allows_configured_origin_and_rejects_other_origin():
    allowed = client.options(
        "/health/live",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    rejected = client.options(
        "/health/live",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert rejected.headers.get("access-control-allow-origin") is None


def test_logout_revokes_refresh_token_and_access_token():
    email = "phase1b-logout@example.com"
    registration = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "Madar!Secure2026",
            "display_name": "Phase 1B",
            "tenant_code": "phase1b-logout",
            "tenant_name": "Phase 1B Logout",
        },
    )
    assert registration.status_code == 201, registration.text
    login = client.post("/auth/login", json={"email": email, "password": "Madar!Secure2026"})
    assert login.status_code == 200, login.text
    tokens = login.json()

    logged_out = client.post(
        "/auth/logout",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert logged_out.status_code == 200
    assert client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401
    assert client.get("/suppliers", headers={"Authorization": f"Bearer {tokens['access_token']}"}).status_code == 401
