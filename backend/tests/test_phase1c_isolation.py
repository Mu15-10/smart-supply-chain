from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _register(prefix: str) -> tuple[str, dict]:
    suffix = uuid.uuid4().hex[:10]
    response = client.post(
        "/auth/register",
        json={
            "email": f"{prefix}-{suffix}@example.com",
            "password": "Madar!Secure2026",
            "display_name": prefix,
            "tenant_code": f"{prefix}-{suffix}",
            "tenant_name": f"{prefix} tenant",
        },
    )
    assert response.status_code == 201, response.text
    token = client.post(
        "/auth/login",
        json={"email": f"{prefix}-{suffix}@example.com", "password": "Madar!Secure2026"},
    )
    assert token.status_code == 200, token.text
    return response.json()["data"]["tenant_id"], token.json()


def _headers(tokens: dict, key: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    if key:
        headers["Idempotency-Key"] = key
    return headers


def _resources(tokens: dict, prefix: str) -> dict[str, dict]:
    headers = _headers(tokens)
    supplier = client.post(
        "/suppliers",
        headers=headers,
        json={"supplier_code": f"SUP-{prefix}-{uuid.uuid4().hex[:8]}", "legal_name": f"{prefix} supplier"},
    )
    warehouse = client.post(
        "/warehouses",
        headers=headers,
        json={"code": f"WH-{prefix}-{uuid.uuid4().hex[:8]}", "name": f"{prefix} warehouse"},
    )
    product = client.post(
        "/products",
        headers=headers,
        json={"sku": f"SKU-{prefix}-{uuid.uuid4().hex[:8]}", "name": f"{prefix} product"},
    )
    assert supplier.status_code == 201, supplier.text
    assert warehouse.status_code == 201, warehouse.text
    assert product.status_code == 201, product.text
    return {
        "supplier": supplier.json()["data"],
        "warehouse": warehouse.json()["data"],
        "product": product.json()["data"],
    }


def _create_po(tokens: dict, resources: dict[str, dict], key: str) -> dict:
    response = client.post(
        "/purchase-orders",
        headers=_headers(tokens, key),
        json={
            "supplier_id": resources["supplier"]["id"],
            "warehouse_id": resources["warehouse"]["id"],
            "lines": [{"product_id": resources["product"]["id"], "ordered_qty": "2", "unit_price": "10"}],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def test_tenant_lists_and_nested_resources_are_isolated():
    # Models PostgreSQL-backed tenant predicates: a token from tenant A must not enumerate tenant B resources.
    tenant_a, tokens_a = _register("isolation-a")
    tenant_b, tokens_b = _register("isolation-b")
    resources_a = _resources(tokens_a, "a")
    resources_b = _resources(tokens_b, "b")
    po_a = _create_po(tokens_a, resources_a, "isolation-po-a")
    po_b = _create_po(tokens_b, resources_b, "isolation-po-b")

    assert tenant_a != tenant_b
    for path, resource_key in (
        ("/suppliers", "supplier"),
        ("/products", "product"),
        ("/warehouses", "warehouse"),
    ):
        visible_to_a = client.get(path, headers=_headers(tokens_a))
        visible_to_b = client.get(path, headers=_headers(tokens_b))
        assert visible_to_a.status_code == 200
        assert visible_to_b.status_code == 200
        assert resources_a[resource_key]["id"] in {row["id"] for row in visible_to_a.json()["data"]}
        assert resources_b[resource_key]["id"] not in {row["id"] for row in visible_to_a.json()["data"]}
        assert resources_b[resource_key]["id"] in {row["id"] for row in visible_to_b.json()["data"]}
        assert resources_a[resource_key]["id"] not in {row["id"] for row in visible_to_b.json()["data"]}

    orders_a = client.get("/purchase-orders", headers=_headers(tokens_a)).json()["data"]
    orders_b = client.get("/purchase-orders", headers=_headers(tokens_b)).json()["data"]
    assert po_a["id"] in {row["id"] for row in orders_a}
    assert po_b["id"] not in {row["id"] for row in orders_a}
    assert po_b["id"] in {row["id"] for row in orders_b}
    assert po_a["id"] not in {row["id"] for row in orders_b}


def test_nested_bola_returns_404_and_does_not_create_cross_tenant_resources():
    # Models BOLA against nested supplier/product/warehouse identifiers; missing tenant ownership is 404.
    _, tokens_a = _register("bola-a")
    _, tokens_b = _register("bola-b")
    resources_a = _resources(tokens_a, "bola-a")
    resources_b = _resources(tokens_b, "bola-b")

    cross_inventory = client.post(
        "/inventory/adjust",
        headers=_headers(tokens_a, "bola-cross-inventory"),
        json={
            "warehouse_id": resources_b["warehouse"]["id"],
            "product_id": resources_b["product"]["id"],
            "quantity": "1",
        },
    )
    assert cross_inventory.status_code == 404

    cross_po = client.post(
        "/purchase-orders",
        headers=_headers(tokens_a, "bola-cross-po"),
        json={
            "supplier_id": resources_b["supplier"]["id"],
            "warehouse_id": resources_a["warehouse"]["id"],
            "lines": [{"product_id": resources_b["product"]["id"], "ordered_qty": "1", "unit_price": "1"}],
        },
    )
    assert cross_po.status_code == 404

    own_po = _create_po(tokens_a, resources_a, "bola-own-po")
    cross_transition = client.post(f"/purchase-orders/{own_po['id']}/submit", headers=_headers(tokens_b))
    assert cross_transition.status_code == 404


def test_same_idempotency_key_isolated_by_tenant():
    # Models PostgreSQL uniqueness on (tenant_id, route, key): identical keys in separate tenants do not collide.
    _, tokens_a = _register("idem-a")
    _, tokens_b = _register("idem-b")
    resources_a = _resources(tokens_a, "idem-a")
    resources_b = _resources(tokens_b, "idem-b")
    key = "same-key-different-tenants"

    for tokens, resources in ((tokens_a, resources_a), (tokens_b, resources_b)):
        response = client.post(
            "/inventory/adjust",
            headers=_headers(tokens, key),
            json={
                "warehouse_id": resources["warehouse"]["id"],
                "product_id": resources["product"]["id"],
                "quantity": "1",
            },
        )
        assert response.status_code == 201, response.text
