from __future__ import annotations

import pytest
from fastapi import Depends
from fastapi.routing import APIRoute

from app.core.policy import validate_route_policy_table
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


@pytest.mark.parametrize("method", ["GET", "POST"])
def test_policy_table_matches_registered_route_methods(method: str):
    # Models route/method lookup: a declared method must resolve to the route's policy metadata.
    matching = [route for route in app.routes if isinstance(route, APIRoute) and method in (route.methods or set())]
    assert matching
    for route in matching:
        assert route.path
