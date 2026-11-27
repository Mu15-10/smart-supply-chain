from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
from sqlalchemy import inspect

from app.main import app, engine

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


def _assert_bola_404(response, *hidden_ids: str):
    assert response.status_code == 404
    assert response.json().get("detail") in {"RESOURCE_NOT_FOUND", "PURCHASE_ORDER_NOT_FOUND"}
    assert all(identifier not in response.text for identifier in hidden_ids)
    assert all(identifier not in value for value in response.headers.values() for identifier in hidden_ids)


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
    _assert_bola_404(
        cross_inventory,
        resources_b["warehouse"]["id"],
        resources_b["product"]["id"],
    )
    cross_inventory_product_only = client.post(
        "/inventory/adjust",
        headers=_headers(tokens_a, "bola-cross-inventory-product-only"),
        json={
            "warehouse_id": resources_a["warehouse"]["id"],
            "product_id": resources_b["product"]["id"],
            "quantity": "1",
        },
    )
    _assert_bola_404(cross_inventory_product_only, resources_b["product"]["id"])
    cross_inventory_warehouse_only = client.post(
        "/inventory/adjust",
        headers=_headers(tokens_a, "bola-cross-inventory-warehouse-only"),
        json={
            "warehouse_id": resources_b["warehouse"]["id"],
            "product_id": resources_a["product"]["id"],
            "quantity": "1",
        },
    )
    _assert_bola_404(cross_inventory_warehouse_only, resources_b["warehouse"]["id"])

    cross_po = client.post(
        "/purchase-orders",
        headers=_headers(tokens_a, "bola-cross-po"),
        json={
            "supplier_id": resources_b["supplier"]["id"],
            "warehouse_id": resources_a["warehouse"]["id"],
            "lines": [{"product_id": resources_b["product"]["id"], "ordered_qty": "1", "unit_price": "1"}],
        },
    )
    _assert_bola_404(cross_po, resources_b["supplier"]["id"], resources_b["product"]["id"])
    for key, supplier_id, warehouse_id, product_id in (
        (
            "bola-cross-po-supplier-only",
            resources_b["supplier"]["id"],
            resources_a["warehouse"]["id"],
            resources_a["product"]["id"],
        ),
        (
            "bola-cross-po-warehouse-only",
            resources_a["supplier"]["id"],
            resources_b["warehouse"]["id"],
            resources_a["product"]["id"],
        ),
        (
            "bola-cross-po-product-only",
            resources_a["supplier"]["id"],
            resources_a["warehouse"]["id"],
            resources_b["product"]["id"],
        ),
    ):
        response = client.post(
            "/purchase-orders",
            headers=_headers(tokens_a, key),
            json={
                "supplier_id": supplier_id,
                "warehouse_id": warehouse_id,
                "lines": [{"product_id": product_id, "ordered_qty": "1", "unit_price": "1"}],
            },
        )
        _assert_bola_404(response, supplier_id, warehouse_id, product_id)

    own_po = _create_po(tokens_a, resources_a, "bola-own-po")
    cross_transition = client.post(f"/purchase-orders/{own_po['id']}/submit", headers=_headers(tokens_b))
    _assert_bola_404(cross_transition, own_po["id"])


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


def test_same_idempotency_key_concurrently_isolated_by_tenant():
    # Models two tenants concurrently claiming one external operation key; PostgreSQL uniqueness includes tenant_id.
    _, tokens_a = _register("idem-concurrent-a")
    _, tokens_b = _register("idem-concurrent-b")
    resources_a = _resources(tokens_a, "idem-concurrent-a")
    resources_b = _resources(tokens_b, "idem-concurrent-b")
    key = "same-concurrent-key-different-tenants"

    def adjust_for(pair: tuple[dict, dict[str, dict]]):
        tokens, resources = pair
        return client.post(
            "/inventory/adjust",
            headers=_headers(tokens, key),
            json={
                "warehouse_id": resources["warehouse"]["id"],
                "product_id": resources["product"]["id"],
                "quantity": "1",
            },
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(adjust_for, ((tokens_a, resources_a), (tokens_b, resources_b))))
    assert [response.status_code for response in responses] == [201, 201]


def test_idempotency_constraint_is_tenant_route_key_scoped():
    # Models the database contract rather than trusting only application-level duplicate handling.
    unique_constraints = inspect(engine).get_unique_constraints("idempotency_keys")
    assert any(
        constraint["name"] == "uq_idem_tenant_route_key" and constraint["column_names"] == ["tenant_id", "route", "key"]
        for constraint in unique_constraints
    )
