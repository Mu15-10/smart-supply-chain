from __future__ import annotations

import uuid

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
SERVER_OWNED_FIELDS = ("tenant_id", "roles", "status", "id", "is_active", "version")


def _admin_tokens() -> dict:
    suffix = uuid.uuid4().hex[:10]
    payload = {
        "email": f"matrix-{suffix}@example.com",
        "password": "Madar!Secure2026",
        "display_name": "matrix",
        "tenant_code": f"matrix-{suffix}",
        "tenant_name": "matrix tenant",
    }
    registered = client.post("/auth/register", json=payload)
    assert registered.status_code == 201, registered.text
    logged_in = client.post("/auth/login", json={"email": payload["email"], "password": payload["password"]})
    assert logged_in.status_code == 200, logged_in.text
    return logged_in.json()


def _valid_body(path: str) -> dict:
    bodies = {
        "/auth/register": {
            "email": "matrix-body@example.com",
            "password": "Madar!Secure2026",
            "display_name": "matrix",
            "tenant_code": "matrix-body",
            "tenant_name": "matrix body tenant",
        },
        "/auth/login": {"email": "matrix-body@example.com", "password": "Madar!Secure2026"},
        "/auth/refresh": {"refresh_token": "x" * 24},
        "/auth/logout": {"refresh_token": "x" * 24},
        "/auth/invitations": {"email": "invite-matrix@example.com", "role": "viewer"},
        "/auth/accept-invitation": {
            "token": "x" * 24,
            "password": "Madar!Secure2026",
            "display_name": "matrix",
        },
        "/suppliers": {"supplier_code": "MATRIX-SUP", "legal_name": "Matrix supplier"},
        "/products": {"sku": "MATRIX-SKU", "name": "Matrix product"},
        "/warehouses": {"code": "MATRIX-WH", "name": "Matrix warehouse"},
        "/inventory/adjust": {"warehouse_id": "w", "product_id": "p", "quantity": "1"},
        "/purchase-orders": {
            "supplier_id": "s",
            "warehouse_id": "w",
            "lines": [{"product_id": "p", "ordered_qty": "1", "unit_price": "1"}],
        },
    }
    return bodies[path].copy()


def _body_routes_with_contracts() -> list[tuple[str, str]]:
    # Models route-derived HTTP coverage: the route registry, not a handwritten endpoint list, drives cases.
    cases: list[tuple[str, str]] = []
    for route in app.routes:
        if not isinstance(route, APIRoute) or "POST" not in (route.methods or set()):
            continue
        if not route.dependant.body_params or route.path not in {
            "/auth/register",
            "/auth/login",
            "/auth/refresh",
            "/auth/logout",
            "/auth/invitations",
            "/auth/accept-invitation",
            "/suppliers",
            "/products",
            "/warehouses",
            "/inventory/adjust",
            "/purchase-orders",
        }:
            continue
        cases.append((route.path, "POST"))
    return cases


@pytest.mark.parametrize(("path", "method"), _body_routes_with_contracts())
@pytest.mark.parametrize("field", SERVER_OWNED_FIELDS)
def test_http_mass_assignment_is_rejected_for_every_generated_body_route(path: str, method: str, field: str):
    # Models an attacker adding server-owned fields to a valid HTTP body; source is Pydantic extra=forbid contract.
    tokens = _admin_tokens()
    body = _valid_body(path)
    body[field] = "attacker"
    headers = (
        {"Authorization": f"Bearer {tokens['access_token']}"}
        if path
        not in {
            "/auth/register",
            "/auth/login",
            "/auth/refresh",
            "/auth/accept-invitation",
        }
        else {}
    )
    response = client.request(method, path, headers=headers, json=body)
    assert response.status_code == 422, (path, field, response.text)
