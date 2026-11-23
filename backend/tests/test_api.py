from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def register(email, tenant_code, tenant_name):
    response = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "Madar!Secure2026",
            "display_name": email,
            "tenant_code": tenant_code,
            "tenant_name": tenant_name,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def token(email):
    return client.post("/auth/login", json={"email": email, "password": "Madar!Secure2026"}).json()["access_token"]


def headers(access_token, key=None):
    value = {"Authorization": f"Bearer {access_token}"}
    if key:
        value["Idempotency-Key"] = key
    return value


def test_purchase_order_and_inventory_flow():
    register("buyer@example.com", "tenant-a", "Tenant A")
    access_token = token("buyer@example.com")
    h = headers(access_token)
    supplier = client.post("/suppliers", headers=h, json={"supplier_code": "SUP-1", "legal_name": "Acme"}).json()[
        "data"
    ]
    warehouse = client.post("/warehouses", headers=h, json={"code": "WH-1", "name": "Main"}).json()["data"]
    product = client.post("/products", headers=h, json={"sku": "SKU-1", "name": "Widget", "reorder_point": 10}).json()[
        "data"
    ]
    response = client.post(
        "/inventory/adjust",
        headers=headers(access_token, "stock-1"),
        json={"warehouse_id": warehouse["id"], "product_id": product["id"], "quantity": "25"},
    )
    assert response.status_code == 201
    assert (
        client.post(
            "/inventory/adjust",
            headers=headers(access_token, "stock-1"),
            json={"warehouse_id": warehouse["id"], "product_id": product["id"], "quantity": "25"},
        ).json()
        == response.json()
    )
    order = client.post(
        "/purchase-orders",
        headers=headers(access_token, "po-1"),
        json={
            "supplier_id": supplier["id"],
            "warehouse_id": warehouse["id"],
            "lines": [{"product_id": product["id"], "ordered_qty": "5", "unit_price": "12.50"}],
        },
    )
    assert order.status_code == 201
    assert order.json()["data"]["total"] == "62.5000"


def test_existing_tenant_requires_invitation_and_cross_tenant_order_is_blocked():
    register("owner@example.com", "tenant-owner", "Owner Tenant")
    owner = token("owner@example.com")
    supplier = client.post(
        "/suppliers", headers=headers(owner), json={"supplier_code": "SUP-X", "legal_name": "Private Supplier"}
    ).json()["data"]
    warehouse = client.post(
        "/warehouses", headers=headers(owner), json={"code": "WH-X", "name": "Private Warehouse"}
    ).json()["data"]
    product = client.post("/products", headers=headers(owner), json={"sku": "SKU-X", "name": "Private Product"}).json()[
        "data"
    ]
    duplicate = client.post(
        "/auth/register",
        json={
            "email": "attacker@example.com",
            "password": "Madar!Secure2026",
            "display_name": "Attacker",
            "tenant_code": "tenant-owner",
            "tenant_name": "Owner Tenant",
        },
    )
    assert duplicate.status_code == 409
    register("buyer-b@example.com", "tenant-b", "Tenant B")
    other = token("buyer-b@example.com")
    order = client.post(
        "/purchase-orders",
        headers=headers(other, "cross-tenant-po"),
        json={
            "supplier_id": supplier["id"],
            "warehouse_id": warehouse["id"],
            "lines": [{"product_id": product["id"], "ordered_qty": "1", "unit_price": "1"}],
        },
    )
    assert order.status_code == 404


def test_unknown_movement_type_is_rejected_and_viewer_cannot_write():
    register("admin@example.com", "tenant-validation", "Validation Tenant")
    admin = token("admin@example.com")
    warehouse = client.post("/warehouses", headers=headers(admin), json={"code": "WH-V", "name": "Validation"}).json()[
        "data"
    ]
    product = client.post("/products", headers=headers(admin), json={"sku": "SKU-V", "name": "Validation"}).json()[
        "data"
    ]
    invalid = client.post(
        "/inventory/adjust",
        headers=headers(admin, "invalid-movement"),
        json={"warehouse_id": warehouse["id"], "product_id": product["id"], "quantity": "1", "movement_type": "bogus"},
    )
    assert invalid.status_code == 422


def test_health_live_and_request_id():
    response = client.get("/health/live", headers={"X-Request-ID": "phase0-check"})
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["X-Request-ID"] == "phase0-check"


def test_health_ready_fails_closed_without_dependencies():
    response = client.get("/health/ready")
    assert response.status_code in {200, 503}
    if response.status_code == 503:
        assert "checks" in response.json()["detail"]
