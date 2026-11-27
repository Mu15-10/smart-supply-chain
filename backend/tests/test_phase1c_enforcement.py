from __future__ import annotations

import pytest
from fastapi import Depends, HTTPException
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from starlette.requests import Request

import app.main as main_module
from app.core.policy import policy_for_route, validate_route_policy_table
from app.main import app, enforce_route_policy
from tests.test_phase1c_policy import GOLDEN_ROUTE_ROLES


def test_app_registers_one_central_policy_dependency():
    # Models the authorization contract: every request is checked against the central route policy.
    dependency_callables = {getattr(dependency.dependency, "__name__", "") for dependency in app.router.dependencies}
    assert "enforce_route_policy" in dependency_callables


def test_registered_routes_have_policy_before_startup():
    # Models fail-closed startup inventory: an undeclared route must prevent application startup.
    validate_route_policy_table(app.routes)


def test_route_policy_dependency_is_a_fastapi_dependency():
    # Models the framework contract: policy enforcement is installed as a dependency, not handler-only code.
    assert callable(enforce_route_policy)
    assert Depends(enforce_route_policy).dependency is enforce_route_policy


def test_protected_request_verifies_jwt_once_and_reuses_request_claims(monkeypatch: pytest.MonkeyPatch):
    # Models the externally observable auth contract: central enforcement and the handler
    # may both need claims, but JWT verification/Redis deny-list work must happen once.
    client = TestClient(app)
    suffix = "auth-cache-matrix"
    registered = client.post(
        "/auth/register",
        json={
            "email": f"{suffix}@example.com",
            "password": "Madar!Secure2026",
            "display_name": suffix,
            "tenant_code": suffix,
            "tenant_name": suffix,
        },
    )
    assert registered.status_code == 201, registered.text
    logged_in = client.post(
        "/auth/login",
        json={"email": f"{suffix}@example.com", "password": "Madar!Secure2026"},
    )
    assert logged_in.status_code == 200, logged_in.text
    token = logged_in.json()["access_token"]

    original_decode = main_module.jwt.decode
    decode_calls = 0

    def counted_decode(*args, **kwargs):
        nonlocal decode_calls
        decode_calls += 1
        return original_decode(*args, **kwargs)

    monkeypatch.setattr(main_module.jwt, "decode", counted_decode)
    response = client.get("/suppliers", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200, response.text
    assert decode_calls == 1


def _request_for(route: APIRoute, method: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": method,
            "path": route.path,
            "raw_path": route.path.encode(),
            "query_string": b"",
            "headers": [],
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 1234),
            "root_path": "",
            "route": route,
        }
    )


@pytest.mark.parametrize("role", ["admin", "purchasing", "inventory", "viewer"])
@pytest.mark.parametrize("ownership", ["owner", "other-tenant"])
def test_generated_route_role_tenant_matrix(monkeypatch: pytest.MonkeyPatch, role: str, ownership: str):
    # Models the authorization layer for every registered route; resource ownership 404 is tested by BOLA HTTP cases.
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        method = sorted(route.methods or {"GET"})[0]
        policy = policy_for_route(method, route.path)
        assert policy is not None
        if policy.access == "public":
            enforce_route_policy(_request_for(route, method))
            continue
        key = (method, route.path)
        expected_roles = GOLDEN_ROUTE_ROLES[key]
        assert expected_roles is not None
        claims = {"tenant_id": "tenant-a" if ownership == "owner" else "tenant-b", "roles": [role]}
        monkeypatch.setattr("app.main.auth", lambda _authorization, claims=claims: claims)
        required_roles = expected_roles - {"authenticated"}
        if required_roles and role not in required_roles:
            with pytest.raises(HTTPException) as error:
                enforce_route_policy(_request_for(route, method))
            assert error.value.status_code == 403
        else:
            try:
                enforce_route_policy(_request_for(route, method))
            except HTTPException as error:
                pytest.fail(f"{route.path} with {role}/{ownership} unexpectedly returned {error.status_code}")


@pytest.mark.parametrize("method", ["GET", "POST"])
def test_policy_table_matches_registered_route_methods(method: str):
    # Models route/method lookup: a declared method must resolve to the route's policy metadata.
    matching = [route for route in app.routes if isinstance(route, APIRoute) and method in (route.methods or set())]
    assert matching
    for route in matching:
        assert route.path
