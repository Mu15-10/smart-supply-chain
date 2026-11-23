import os
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.main import app

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires PostgreSQL"),
]


def _headers(token: str, key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Idempotency-Key": key}


def _setup():
    client = TestClient(app)
    registration = client.post(
        "/auth/register",
        json={
            "email": "concurrency@example.com",
            "password": "Madar!Secure2026",
            "display_name": "Concurrency",
            "tenant_code": "tenant-concurrency",
            "tenant_name": "Concurrency Tenant",
        },
    )
    assert registration.status_code == 201, registration.text
    login = client.post("/auth/login", json={"email": "concurrency@example.com", "password": "Madar!Secure2026"})
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    supplier = client.post(
        "/suppliers", headers=headers, json={"supplier_code": "SUP-C", "legal_name": "Concurrent Supplier"}
    ).json()["data"]
    warehouse = client.post(
        "/warehouses", headers=headers, json={"code": "WH-C", "name": "Concurrent Warehouse"}
    ).json()["data"]
    product = client.post("/products", headers=headers, json={"sku": "SKU-C", "name": "Concurrent Product"}).json()[
        "data"
    ]
    return client, token, supplier, warehouse, product


def _post_order(client, token, supplier, warehouse, product, key):
    return client.post(
        "/purchase-orders",
        headers=_headers(token, key),
        json={
            "supplier_id": supplier["id"],
            "warehouse_id": warehouse["id"],
            "lines": [{"product_id": product["id"], "ordered_qty": "1", "unit_price": "2"}],
        },
    )


def test_concurrent_purchase_orders_on_postgres():
    client, token, supplier, warehouse, product = _setup()
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(
                lambda key: _post_order(client, token, supplier, warehouse, product, key),
                ["po-concurrent-1", "po-concurrent-2"],
            )
        )
    assert [response.status_code for response in responses] == [201, 201]
    assert len({response.json()["data"]["id"] for response in responses}) == 2


def test_concurrent_inventory_adjustments_preserve_postgres_row_locking():
    client, token, supplier, warehouse, product = _setup()
    headers = {"Authorization": f"Bearer {token}"}
    seed = client.post(
        "/inventory/adjust",
        headers={**headers, "Idempotency-Key": "inventory-seed"},
        json={"warehouse_id": warehouse["id"], "product_id": product["id"], "quantity": "10"},
    )
    assert seed.status_code == 201, seed.text

    def issue(key):
        return client.post(
            "/inventory/adjust",
            headers={**headers, "Idempotency-Key": key},
            json={
                "warehouse_id": warehouse["id"],
                "product_id": product["id"],
                "quantity": "4",
                "movement_type": "issue",
            },
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(issue, ["inventory-issue-1", "inventory-issue-2"]))
    assert [response.status_code for response in responses] == [201, 201]
    inventory = client.get("/inventory", headers=headers).json()["data"]
    assert inventory[0]["onHand"] == "2.0000"


def test_concurrent_same_idempotency_key_has_one_committed_order():
    client, token, supplier, warehouse, product = _setup()
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(
                lambda _: _post_order(client, token, supplier, warehouse, product, "po-same-key"),
                [1, 2],
            )
        )
    assert [response.status_code for response in responses] == [201, 201]
    assert len({response.json()["data"]["id"] for response in responses}) == 1
    orders = client.get("/purchase-orders", headers={"Authorization": f"Bearer {token}"}).json()["data"]
    assert len(orders) == 1


def test_concurrent_refresh_of_same_token_has_one_success_and_one_reuse_detection():
    client, _, _, _, _ = _setup()
    login = client.post("/auth/login", json={"email": "concurrency@example.com", "password": "Madar!Secure2026"})
    assert login.status_code == 200, login.text
    refresh_token = login.json()["refresh_token"]

    def rotate(_):
        return client.post("/auth/refresh", json={"refresh_token": refresh_token})

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(rotate, [1, 2]))

    assert sorted(response.status_code for response in responses) == [200, 401]
    failed = next(response for response in responses if response.status_code == 401)
    assert failed.json()["detail"] == "REFRESH_TOKEN_REUSE_DETECTED"
