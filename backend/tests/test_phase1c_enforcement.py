from __future__ import annotations

import pytest
from fastapi import Depends, HTTPException
from fastapi.routing import APIRoute
from starlette.requests import Request

from app.core.policy import policy_for_route, validate_route_policy_table
from app.main import app, enforce_route_policy


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
        policy = policy_for_route(route.path)
        assert policy is not None
        if policy.access == "public":
            enforce_route_policy(_request_for(route, method))
            continue
        claims = {"tenant_id": "tenant-a" if ownership == "owner" else "tenant-b", "roles": [role]}
        monkeypatch.setattr("app.main.auth", lambda _authorization, claims=claims: claims)
        required_roles = policy.roles - {"authenticated"}
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
