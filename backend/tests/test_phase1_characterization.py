import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _identity(prefix: str) -> tuple[str, str, str]:
    suffix = uuid.uuid4().hex[:10]
    return f"{prefix}-{suffix}@example.com", f"tenant-{prefix}-{suffix}", f"{prefix.title()} Tenant"


def _register(prefix: str = "phase1") -> tuple[dict, dict]:
    email, tenant_code, tenant_name = _identity(prefix)
    response = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "Madar!Secure2026",
            "display_name": prefix.title(),
            "tenant_code": tenant_code,
            "tenant_name": tenant_name,
        },
    )
    assert response.status_code == 201, response.text
    login = client.post("/auth/login", json={"email": email, "password": "Madar!Secure2026"})
    assert login.status_code == 200, login.text
    return response.json()["data"], login.json()


def _headers(access_token: str, key: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {access_token}"}
    if key:
        headers["Idempotency-Key"] = key
    return headers


def _resources(access_token: str) -> dict[str, dict]:
    headers = _headers(access_token)
    supplier = client.post(
        "/suppliers",
        headers=headers,
        json={"supplier_code": f"SUP-{uuid.uuid4().hex[:8]}", "legal_name": "Phase 1 Supplier"},
    )
    warehouse = client.post(
        "/warehouses", headers=headers, json={"code": f"WH-{uuid.uuid4().hex[:8]}", "name": "Phase 1 Warehouse"}
    )
    product = client.post(
        "/products", headers=headers, json={"sku": f"SKU-{uuid.uuid4().hex[:8]}", "name": "Phase 1 Product"}
    )
    assert supplier.status_code == 201, supplier.text
    assert warehouse.status_code == 201, warehouse.text
    assert product.status_code == 201, product.text
    return {
        "supplier": supplier.json()["data"],
        "warehouse": warehouse.json()["data"],
        "product": product.json()["data"],
    }


def test_phase1_public_health_and_security_headers():
    live = client.get("/health/live", headers={"X-Request-ID": "phase1-check"})
    assert live.status_code == 200
    assert live.json() == {"status": "ok"}
    assert live.headers["X-Request-ID"] == "phase1-check"
    assert live.headers["X-Content-Type-Options"] == "nosniff"
    assert live.headers["X-Frame-Options"] == "DENY"
    assert live.headers["Referrer-Policy"] == "no-referrer"

    health = client.get("/health")
    assert health.status_code == 200
    assert set(health.json()) == {"status", "service", "environment"}


def test_phase1_auth_refresh_rotation_and_logout():
    _, tokens = _register("auth")
    access = tokens["access_token"]
    refresh = tokens["refresh_token"]
    assert tokens["token_type"] == "bearer"  # noqa: S105 - characterization of response shape
    assert client.get("/suppliers", headers=_headers(access)).status_code == 200

    rotated = client.post("/auth/refresh", json={"refresh_token": refresh})
    assert rotated.status_code == 200, rotated.text
    rotated_tokens = rotated.json()
    assert rotated_tokens["refresh_token"] != refresh

    reused = client.post("/auth/refresh", json={"refresh_token": refresh})
    assert reused.status_code == 401
    assert reused.json()["detail"] == "REFRESH_TOKEN_REUSE_DETECTED"

    logged_out = client.post(
        "/auth/logout",
        headers=_headers(rotated_tokens["access_token"]),
        json={"refresh_token": rotated_tokens["refresh_token"]},
    )
    assert logged_out.status_code == 200
    assert logged_out.json() == {"data": {"logged_out": True}}
    assert client.get("/suppliers", headers=_headers(rotated_tokens["access_token"])).status_code == 401


def test_phase1_auth_validation_and_role_boundaries():
    _, tokens = _register("roles")
    access = tokens["access_token"]
    missing_auth = client.get("/suppliers")
    assert missing_auth.status_code == 401

    invalid_login = client.post("/auth/login", json={"email": "not-an-email", "password": "wrong"})
    assert invalid_login.status_code == 422

    resources = _resources(access)
    viewer_email, viewer_tenant, viewer_name = _identity("viewer")
    invitation = client.post(
        "/auth/invitations",
        headers=_headers(access),
        json={"email": viewer_email, "role": "viewer"},
    )
    assert invitation.status_code == 201, invitation.text
    invitation_data = invitation.json()["data"]
    assert invitation_data["email"] == viewer_email
    assert invitation_data["role"] == "viewer"
    assert "token" in invitation_data

    accepted = client.post(
        "/auth/accept-invitation",
        json={
            "token": invitation_data["token"],
            "password": "Madar!Viewer2026",
            "display_name": viewer_name,
        },
    )
    assert accepted.status_code == 201, accepted.text
    viewer_login = client.post("/auth/login", json={"email": viewer_email, "password": "Madar!Viewer2026"})
    assert viewer_login.status_code == 200
    viewer_token = viewer_login.json()["access_token"]
    denied = client.post(
        "/products",
        headers=_headers(viewer_token),
        json={"sku": "VIEWER-SKU", "name": "Viewer cannot write"},
    )
    assert denied.status_code == 403

    for path in ("/suppliers", "/products", "/warehouses", "/inventory", "/purchase-orders"):
        response = client.get(path, headers=_headers(access))
        assert response.status_code == 200, (path, response.text)
        assert "data" in response.json()
    assert resources["supplier"]["id"]


def test_phase1_inventory_and_purchase_order_transition_shapes():
    _, tokens = _register("flow")
    access = tokens["access_token"]
    resources = _resources(access)
    headers = _headers(access)
    inventory = client.post(
        "/inventory/adjust",
        headers=_headers(access, "phase1-inventory"),
        json={
            "warehouse_id": resources["warehouse"]["id"],
            "product_id": resources["product"]["id"],
            "quantity": "12",
        },
    )
    assert inventory.status_code == 201, inventory.text
    assert set(inventory.json()["data"]) == {"warehouseId", "productId", "onHand", "reserved", "available"}

    order = client.post(
        "/purchase-orders",
        headers=_headers(access, "phase1-po"),
        json={
            "supplier_id": resources["supplier"]["id"],
            "warehouse_id": resources["warehouse"]["id"],
            "lines": [{"product_id": resources["product"]["id"], "ordered_qty": "5", "unit_price": "12.50"}],
        },
    )
    assert order.status_code == 201, order.text
    order_data = order.json()["data"]
    assert order_data["status"] == "draft"
    assert order_data["total"] == "62.5000"

    po_id = order_data["id"]
    submitted = client.post(f"/purchase-orders/{po_id}/submit", headers=headers)
    approved = client.post(f"/purchase-orders/{po_id}/approve", headers=headers)
    received = client.post(f"/purchase-orders/{po_id}/receive", headers=_headers(access, "phase1-receive"))
    assert submitted.status_code == 200 and submitted.json()["data"]["status"] == "pending_approval"
    assert approved.status_code == 200 and approved.json()["data"]["status"] == "approved"
    assert received.status_code == 200 and received.json()["data"]["status"] == "received"

    invalid_transition = client.post(f"/purchase-orders/{po_id}/approve", headers=headers)
    assert invalid_transition.status_code == 409


def test_phase1_missing_resources_and_idempotency_conflicts():
    _, tokens = _register("errors")
    access = tokens["access_token"]
    missing = client.post(
        "/inventory/adjust",
        headers=_headers(access, "phase1-missing"),
        json={"warehouse_id": "missing", "product_id": "missing", "quantity": "1"},
    )
    assert missing.status_code == 404

    resources = _resources(access)
    payload = {
        "warehouse_id": resources["warehouse"]["id"],
        "product_id": resources["product"]["id"],
        "quantity": "1",
    }
    first = client.post("/inventory/adjust", headers=_headers(access, "phase1-conflict"), json=payload)
    changed = client.post(
        "/inventory/adjust",
        headers=_headers(access, "phase1-conflict"),
        json={**payload, "quantity": "2"},
    )
    assert first.status_code == 201
    assert changed.status_code == 409
    assert changed.json()["detail"] == "IDEMPOTENCY_KEY_REUSED"


@pytest.mark.parametrize(
    ("path", "method"),
    [
        ("/health/live", "get"),
        ("/health/ready", "get"),
        ("/health", "get"),
        ("/auth/register", "post"),
        ("/auth/login", "post"),
        ("/auth/refresh", "post"),
        ("/auth/logout", "post"),
        ("/auth/invitations", "post"),
        ("/auth/accept-invitation", "post"),
        ("/suppliers", "get"),
        ("/products", "get"),
        ("/warehouses", "get"),
        ("/inventory", "get"),
        ("/purchase-orders", "get"),
    ],
)
def test_phase1_endpoint_routes_are_registered(path: str, method: str):
    routes = {(route.path, method) for route in app.routes for method in getattr(route, "methods", set())}
    assert (path, method.upper()) in routes
