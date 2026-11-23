from __future__ import annotations

import ipaddress
from contextlib import contextmanager

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

import app.main as main
from app.main import RefreshIn, app

client = TestClient(app)


def _request(
    headers: list[tuple[str, str]] | None = None,
    client_host: str | None = "10.0.0.10",
) -> Request:
    raw_headers = [(key.lower().encode(), value.encode()) for key, value in (headers or [])]
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": raw_headers,
        "client": (client_host, 1234) if client_host else None,
        "server": ("testserver", 80),
    }
    return Request(scope)


def _set_trusted_proxy(monkeypatch: pytest.MonkeyPatch, *cidrs: str) -> None:
    monkeypatch.setattr(main, "TRUSTED_PROXY_NETWORKS", tuple(ipaddress.ip_network(cidr) for cidr in cidrs))


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
    # Models a real refresh request; only the configured proxy-derived client identity enters the key.
    with _patched_refresh_limiter(monkeypatch) as calls:
        with pytest.raises(HTTPException) as raised:
            main.refresh(_request(client_host="10.0.0.20"), RefreshIn(refresh_token="x" * 20))

    assert raised.value.status_code == 401
    assert len(calls) == 2
    assert calls[0][1] == 7
    assert calls[1][1] == 11
    assert all("10.0.0.20" not in key for key, _ in calls)
    assert all(key.startswith("refresh:") for key, _ in calls)


def test_one_proxy_uses_real_client_appended_by_proxy(monkeypatch: pytest.MonkeyPatch):
    # Models nginx/Cloudflare-style appending: the socket peer is the proxy and XFF ends with the client.
    _set_trusted_proxy(monkeypatch, "10.0.0.0/24")
    request = _request([("X-Forwarded-For", "198.51.100.8")], client_host="10.0.0.10")

    assert main.get_client_ip(request) == "198.51.100.8"


def test_one_proxy_ignores_attacker_prefix_and_uses_appended_client(monkeypatch: pytest.MonkeyPatch):
    # Models a client-supplied prefix followed by the proxy's appended client address.
    _set_trusted_proxy(monkeypatch, "10.0.0.0/24")
    request = _request([("X-Forwarded-For", "6.6.6.6, 198.51.100.8")], client_host="10.0.0.10")

    assert main.get_client_ip(request) == "198.51.100.8"


def test_invalid_left_prefix_is_not_analyzed_after_client_is_selected(monkeypatch: pytest.MonkeyPatch):
    # Models a proxy-appended suffix: only the trusted suffix and selected client are parsed;
    # the attacker-controlled prefix is not analyzed. Source: ADR-001/MDN XFF model.
    _set_trusted_proxy(monkeypatch, "10.0.0.0/24")
    request = _request([("X-Forwarded-For", "garbage!!, 198.51.100.8, 10.0.0.10")], client_host="10.0.0.10")

    assert main.get_client_ip(request) == "198.51.100.8"


def test_invalid_left_prefix_with_port_is_not_analyzed(monkeypatch: pytest.MonkeyPatch):
    # Models attacker-controlled XFF prefix data; a port-shaped prefix is ignored after selection.
    _set_trusted_proxy(monkeypatch, "10.0.0.0/24")
    request = _request([("X-Forwarded-For", "6.6.6.6:80, 198.51.100.8, 10.0.0.10")], client_host="10.0.0.10")

    assert main.get_client_ip(request) == "198.51.100.8"


def test_invalid_xff_entry_to_the_right_falls_back(monkeypatch: pytest.MonkeyPatch):
    # Models a malformed value in the proxy-controlled suffix; unlike a left prefix, it is analyzed.
    _set_trusted_proxy(monkeypatch, "10.0.0.0/24")
    request = _request([("X-Forwarded-For", "198.51.100.8, garbage!!")], client_host="10.0.0.10")

    assert main.get_client_ip(request) == "10.0.0.10"


def test_two_and_three_proxies_skip_trusted_suffix(monkeypatch: pytest.MonkeyPatch):
    # Models a chain where each proxy appends its peer; trusted proxy addresses form the right suffix.
    _set_trusted_proxy(monkeypatch, "10.0.0.0/24", "192.0.2.0/24")
    request = _request([("X-Forwarded-For", "198.51.100.8, 10.0.0.11, 192.0.2.11")], client_host="192.0.2.12")
    assert main.get_client_ip(request) == "198.51.100.8"

    xff = "6.6.6.6, 198.51.100.8, 10.0.0.11, 192.0.2.11"
    request = _request([("X-Forwarded-For", xff)], client_host="192.0.2.12")
    assert main.get_client_ip(request) == "198.51.100.8"


def test_ipv6_and_mapped_ipv4_are_normalized(monkeypatch: pytest.MonkeyPatch):
    # Models IPv6 proxy chains and IPv4-mapped addresses accepted by dual-stack sockets.
    _set_trusted_proxy(monkeypatch, "2001:db8:100::/48")
    request = _request([("X-Forwarded-For", "::ffff:198.51.100.8")], client_host="2001:db8:100::10")
    assert main.get_client_ip(request) == "198.51.100.8"
    assert main.rate_limit_ip("2001:db8:abcd:1::8") == "2001:db8:abcd:1::/64"
    assert main.rate_limit_ip("::ffff:198.51.100.8") == "198.51.100.8"


def test_multiple_xff_lines_are_joined_in_wire_order(monkeypatch: pytest.MonkeyPatch):
    # Models proxies emitting multiple XFF header lines; MDN requires one ordered combined list.
    _set_trusted_proxy(monkeypatch, "10.0.0.0/24", "192.0.2.0/24")
    request = _request(
        [("X-Forwarded-For", "198.51.100.8"), ("X-Forwarded-For", "10.0.0.11, 192.0.2.11")],
        client_host="10.0.0.10",
    )
    assert main.get_client_ip(request) == "198.51.100.8"


def test_invalid_and_oversized_xff_fall_back_without_raw_address_logging(monkeypatch: pytest.MonkeyPatch, caplog):
    # Models malformed client-controlled headers; invalid ports, unknown tokens, and oversized chains are rejected.
    _set_trusted_proxy(monkeypatch, "10.0.0.0/24")
    invalid = _request([("X-Forwarded-For", "unknown")], client_host="10.0.0.10")
    assert main.get_client_ip(invalid) == "10.0.0.10"
    assert "unknown" not in caplog.text

    too_many = _request([("X-Forwarded-For", ",".join(["198.51.100.8"] * 65))], client_host="10.0.0.10")
    assert main.get_client_ip(too_many) == "10.0.0.10"
    assert main.CLIENT_IP_FALLBACK_TOTAL["too_many_entries"] >= 1


def test_proxy_peer_outside_cidr_and_missing_peer_ignore_xff(monkeypatch: pytest.MonkeyPatch):
    # Models direct origin access and malformed ASGI client metadata; untrusted peers cannot delegate trust to XFF.
    _set_trusted_proxy(monkeypatch, "10.0.0.0/24")
    request = _request([("X-Forwarded-For", "198.51.100.8")], client_host="203.0.113.10")
    assert main.get_client_ip(request) == "203.0.113.10"
    assert main.get_client_ip(_request([("X-Forwarded-For", "198.51.100.8")], client_host=None)) == "unknown"


def test_empty_and_all_trusted_xff_have_safe_fallback(monkeypatch: pytest.MonkeyPatch):
    # Models a trusted proxy with no forwarding data and a malformed chain containing only infrastructure peers.
    _set_trusted_proxy(monkeypatch, "10.0.0.0/24")
    assert main.get_client_ip(_request(client_host="10.0.0.10")) == "10.0.0.10"
    assert main.get_client_ip(_request([("X-Forwarded-For", "10.0.0.11")], client_host="10.0.0.10")) == "10.0.0.10"
    assert main.CLIENT_IP_FALLBACK_TOTAL["all_trusted"] >= 1


def test_metrics_endpoint_is_not_public():
    # Models an unauthenticated external request; process-local counters are not exposed before monitoring design.
    response = client.get("/metrics")
    assert response.status_code == 404


def test_rotating_spoofed_xff_does_not_bypass_login_registration_or_refresh_limits(monkeypatch: pytest.MonkeyPatch):
    # Models a trusted edge: changing attacker prefixes still carry one appended real client IP.
    _set_trusted_proxy(monkeypatch, "10.0.0.0/24")
    edge_client = TestClient(app, client=("10.0.0.10", 1234))
    assert main.rds is not None
    main.rds.flushdb()

    original_registration = main.settings.registration_max_per_ip
    original_login = main.settings.login_max_per_account_ip
    original_refresh = main.settings.refresh_max_per_ip
    main.settings.registration_max_per_ip = 5
    main.settings.login_max_per_account_ip = 5
    main.settings.refresh_max_per_ip = 2
    try:
        for index in range(5):
            response = edge_client.post(
                "/auth/register",
                headers={"X-Forwarded-For": f"6.6.6.{index}, 198.51.100.8"},
                json={
                    "email": f"xff-register-{index}@example.com",
                    "password": "Madar!Secure2026",
                    "display_name": "XFF",
                    "tenant_code": f"xff-register-{index}",
                    "tenant_name": "XFF",
                },
            )
            assert response.status_code == 201, response.text
        assert (
            edge_client.post(
                "/auth/register",
                headers={"X-Forwarded-For": "6.6.6.99, 198.51.100.8"},
                json={
                    "email": "xff-register-six@example.com",
                    "password": "Madar!Secure2026",
                    "display_name": "XFF",
                    "tenant_code": "xff-register-six",
                    "tenant_name": "XFF",
                },
            ).status_code
            == 429
        )

        email = "xff-login@example.com"
        registration = edge_client.post(
            "/auth/register",
            headers={"X-Forwarded-For": "198.51.100.8"},
            json={
                "email": email,
                "password": "Madar!Secure2026",
                "display_name": "XFF",
                "tenant_code": "xff-login",
                "tenant_name": "XFF",
            },
        )
        assert registration.status_code == 429
        main.rds.flushdb()
        # The invalid password is intentional; account-IP limiting must use the appended client, not the spoofed prefix.
        for index in range(5):
            response = edge_client.post(
                "/auth/login",
                headers={"X-Forwarded-For": f"7.7.7.{index}, 198.51.100.8"},
                json={"email": "xff-register-0@example.com", "password": "wrong"},
            )
            assert response.status_code == 401
        assert (
            edge_client.post(
                "/auth/login",
                headers={"X-Forwarded-For": "7.7.7.99, 198.51.100.8"},
                json={"email": "xff-register-0@example.com", "password": "wrong"},
            ).status_code
            == 429
        )

        main.rds.flushdb()
        for index in range(2):
            assert (
                edge_client.post(
                    "/auth/refresh",
                    headers={"X-Forwarded-For": f"8.8.8.{index}, 198.51.100.8"},
                    json={"refresh_token": "x" * 20},
                ).status_code
                == 401
            )
        assert (
            edge_client.post(
                "/auth/refresh",
                headers={"X-Forwarded-For": "8.8.8.99, 198.51.100.8"},
                json={"refresh_token": "x" * 20},
            ).status_code
            == 429
        )
    finally:
        main.settings.registration_max_per_ip = original_registration
        main.settings.login_max_per_account_ip = original_login
        main.settings.refresh_max_per_ip = original_refresh


def test_removed_proxy_count_is_rejected(monkeypatch: pytest.MonkeyPatch):
    # Models a deployment carrying a removed setting; startup must fail instead of silently weakening trust.
    monkeypatch.setenv("TRUSTED_PROXY_COUNT", "1")
    from app.core.config import Settings

    with pytest.raises(ValueError, match="TRUSTED_PROXY_COUNT was removed"):
        Settings(environment="test", jwt_secret="x" * 32)


def test_redis_availability_fails_closed_in_production(monkeypatch: pytest.MonkeyPatch):
    class BrokenRedis:
        def ping(self):
            raise main.RedisError("redis unavailable")

        def pipeline(self, transaction: bool = True):
            raise main.RedisError("redis unavailable")

    monkeypatch.setattr(main, "rds", BrokenRedis())
    monkeypatch.setattr(main, "ENVIRONMENT", "production")
    with pytest.raises(HTTPException, match="AUTH_TEMPORARILY_UNAVAILABLE") as raised:
        main.redis_available()
    assert raised.value.status_code == 503


def test_cors_allows_configured_origin_and_rejects_other_origin():
    allowed = client.options(
        "/health/live",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
    )
    rejected = client.options(
        "/health/live",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert rejected.headers.get("access-control-allow-origin") is None


def _register_and_login(prefix: str) -> dict:
    email = f"phase1b-{prefix}@example.com"
    registration = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "Madar!Secure2026",
            "display_name": "Phase 1B",
            "tenant_code": f"phase1b-{prefix}",
            "tenant_name": f"Phase 1B {prefix}",
        },
    )
    assert registration.status_code == 201, registration.text
    login = client.post("/auth/login", json={"email": email, "password": "Madar!Secure2026"})
    assert login.status_code == 200, login.text
    return login.json()


def test_logout_revokes_entire_refresh_family_and_unknown_token_is_generic():
    # Models a user logout that invalidates every rotated session generation, without token enumeration.
    # This case alone would not distinguish revoking one token from the whole family because no live child remains.
    tokens = _register_and_login("family")
    rotated = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).json()
    latest = client.post("/auth/refresh", json={"refresh_token": rotated["refresh_token"]}).json()
    logged_out = client.post(
        "/auth/logout",
        headers={"Authorization": f"Bearer {latest['access_token']}"},
        json={"refresh_token": latest["refresh_token"]},
    )
    assert logged_out.status_code == 200
    for refresh_token in (tokens["refresh_token"], rotated["refresh_token"], latest["refresh_token"]):
        assert client.post("/auth/refresh", json={"refresh_token": refresh_token}).status_code == 401

    unknown_tokens = _register_and_login("unknown")
    unknown = client.post(
        "/auth/logout",
        headers={"Authorization": f"Bearer {unknown_tokens['access_token']}"},
        json={"refresh_token": "x" * 64},
    )
    assert unknown.status_code == 200
    assert unknown.json() == {"data": {"logged_out": True}}


def test_logout_with_old_refresh_token_revokes_family_and_does_not_cross_users():
    # Models two users sharing the service: a refresh token from another user must not revoke either family.
    user_a = _register_and_login("logout-old-a")
    user_a_rotated = client.post("/auth/refresh", json={"refresh_token": user_a["refresh_token"]})
    assert user_a_rotated.status_code == 200
    user_a_rotated_data = user_a_rotated.json()
    user_a_rt1 = user_a_rotated_data["refresh_token"]
    user_a_current_access = user_a_rotated_data["access_token"]

    user_b = _register_and_login("logout-old-b")
    wrong_user_logout = client.post(
        "/auth/logout",
        headers={"Authorization": f"Bearer {user_a_current_access}"},
        json={"refresh_token": user_b["refresh_token"]},
    )
    assert wrong_user_logout.status_code == 200
    user_a_rt2_response = client.post("/auth/refresh", json={"refresh_token": user_a_rt1})
    assert user_a_rt2_response.status_code == 200
    user_a_current_access = user_a_rt2_response.json()["access_token"]
    user_b_rotated = client.post("/auth/refresh", json={"refresh_token": user_b["refresh_token"]})
    assert user_b_rotated.status_code == 200
    user_b_current_access = user_b_rotated.json()["access_token"]

    # Reusing revoked generation zero must still find its family and revoke the live descendants.
    old_token_logout = client.post(
        "/auth/logout",
        headers={"Authorization": f"Bearer {user_a_current_access}"},
        json={"refresh_token": user_a["refresh_token"]},
    )
    assert old_token_logout.status_code == 200
    assert client.post("/auth/refresh", json={"refresh_token": user_a_rt1}).status_code == 401

    unknown_logout = client.post(
        "/auth/logout",
        headers={"Authorization": f"Bearer {user_b_current_access}"},
        json={"refresh_token": "x" * 64},
    )
    assert unknown_logout.status_code == 200
    assert unknown_logout.json() == {"data": {"logged_out": True}}


def test_refresh_reuse_after_multiple_generations_revokes_family_and_records_event():
    # Models three rotations followed by reuse of generation zero; all descendants must be revoked and audited.
    tokens = _register_and_login("reuse")
    generations = [tokens]
    for _ in range(3):
        generations.append(
            client.post("/auth/refresh", json={"refresh_token": generations[-1]["refresh_token"]}).json()
        )
    reused = client.post("/auth/refresh", json={"refresh_token": generations[0]["refresh_token"]})
    assert reused.status_code == 401
    assert reused.json()["detail"] == "REFRESH_TOKEN_REUSE_DETECTED"
    for generation in generations[1:]:
        assert client.post("/auth/refresh", json={"refresh_token": generation["refresh_token"]}).status_code == 401

    from sqlalchemy import select

    from app.main import Outbox, engine

    with main.Session(engine) as db:
        event = db.scalar(select(Outbox).where(Outbox.event_type == "security.refresh_token_reuse_detected"))
    assert event is not None
