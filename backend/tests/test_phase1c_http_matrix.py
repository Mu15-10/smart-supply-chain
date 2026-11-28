from __future__ import annotations

import uuid

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.main import app
from tests.test_phase1c_policy import GOLDEN_ROUTE_ROLES

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


def _role_tokens_via_invitation() -> dict[str, dict]:
    """Create one real JWT per role through the public invitation lifecycle."""
    suffix = uuid.uuid4().hex[:10]
    admin_payload = {
        "email": f"role-admin-{suffix}@example.com",
        "password": "Madar!Secure2026",
        "display_name": "role-admin",
        "tenant_code": f"role-{suffix}",
        "tenant_name": "role matrix tenant",
    }
    registered = client.post("/auth/register", json=admin_payload)
    assert registered.status_code == 201, registered.text
    admin_login = client.post(
        "/auth/login", json={"email": admin_payload["email"], "password": admin_payload["password"]}
    )
    assert admin_login.status_code == 200, admin_login.text
    tokens = {"admin": admin_login.json()}
    for role in ("purchasing", "inventory", "viewer"):
        email = f"role-{role}-{suffix}@example.com"
        invitation = client.post(
            "/auth/invitations",
            headers={"Authorization": f"Bearer {tokens['admin']['access_token']}"},
            json={"email": email, "role": role},
        )
        assert invitation.status_code == 201, invitation.text
        invitation_token = invitation.json()["data"]["token"]
        accepted = client.post(
            "/auth/accept-invitation",
            json={"token": invitation_token, "password": "Madar!Secure2026", "display_name": role},
        )
        assert accepted.status_code == 201, accepted.text
        logged_in = client.post("/auth/login", json={"email": email, "password": "Madar!Secure2026"})
        assert logged_in.status_code == 200, logged_in.text
        tokens[role] = logged_in.json()
    return tokens


def _role_matrix_body(path: str, role: str, suffix: str) -> dict:
    bodies = (
        _valid_body(path)
        if path
        in {
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
        }
        else {}
    )
    if path == "/auth/register":
        bodies.update(
            email=f"route-register-{role}-{suffix}@example.com",
            tenant_code=f"route-{role}-{suffix}",
            tenant_name=f"route {role} tenant",
        )
    elif path == "/auth/login":
        bodies.update(email=f"missing-{role}-{suffix}@example.com")
    elif path == "/auth/invitations":
        bodies.update(email=f"route-invite-{role}-{suffix}@example.com")
    return bodies


def test_real_http_role_matrix_covers_invitation_to_jwt_to_policy():
    # Models the external lifecycle: admin invites each role, the invitee accepts and logs in,
    # then every registered method/path is called with that real JWT and compared to golden policy.
    tokens = _role_tokens_via_invitation()
    suffix = uuid.uuid4().hex[:8]
    ordered_routes = sorted(
        (route for route in app.routes if isinstance(route, APIRoute)),
        key=lambda route: route.path == "/auth/logout",
    )
    for route in ordered_routes:
        for method in route.methods or ():
            key = (method, route.path)
            assert key in GOLDEN_ROUTE_ROLES, f"new route requires golden authorization decision: {key}"
            expected_roles = GOLDEN_ROUTE_ROLES[key]
            path = route.path.replace("{po_id}", str(uuid.uuid4()))
            for role, role_tokens in tokens.items():
                headers = {"Authorization": f"Bearer {role_tokens['access_token']}"}
                body = _role_matrix_body(route.path, role, suffix) if method in {"POST", "PUT", "PATCH"} else None
                response = client.request(method, path, headers=headers, json=body)
                expected_forbidden = (
                    expected_roles is not None and "authenticated" not in expected_roles and role not in expected_roles
                )
                assert (response.status_code == 403) == expected_forbidden, (
                    key,
                    role,
                    response.status_code,
                    response.text,
                )
