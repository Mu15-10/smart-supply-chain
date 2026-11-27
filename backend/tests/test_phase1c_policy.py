from __future__ import annotations

import pytest
from fastapi.routing import APIRoute
from pydantic import ValidationError

from app.core.policy import PUBLIC_ROUTE_WHITELIST, policy_for_route
from app.main import (
    AcceptInvitation,
    AdjustIn,
    InvitationIn,
    LineIn,
    Login,
    POIn,
    ProductIn,
    RefreshIn,
    Register,
    SupplierIn,
    WarehouseIn,
    app,
)

GOLDEN_ROUTE_ROLES: dict[tuple[str, str], frozenset[str] | None] = {
    ("GET", "/health/live"): None,
    ("GET", "/health/ready"): None,
    ("GET", "/health"): None,
    ("GET", "/docs"): None,
    ("GET", "/redoc"): None,
    ("GET", "/openapi.json"): None,
    ("GET", "/docs/oauth2-redirect"): None,
    ("POST", "/auth/register"): None,
    ("POST", "/auth/login"): None,
    ("POST", "/auth/refresh"): None,
    ("POST", "/auth/accept-invitation"): None,
    ("POST", "/auth/logout"): frozenset({"authenticated"}),
    ("POST", "/auth/invitations"): frozenset({"admin"}),
    ("GET", "/suppliers"): frozenset({"admin", "purchasing", "inventory", "viewer"}),
    ("POST", "/suppliers"): frozenset({"admin", "purchasing"}),
    ("GET", "/products"): frozenset({"admin", "purchasing", "inventory", "viewer"}),
    ("POST", "/products"): frozenset({"admin", "purchasing", "inventory"}),
    ("GET", "/warehouses"): frozenset({"admin", "purchasing", "inventory", "viewer"}),
    ("POST", "/warehouses"): frozenset({"admin", "inventory"}),
    ("GET", "/inventory"): frozenset({"admin", "purchasing", "inventory", "viewer"}),
    ("POST", "/inventory/adjust"): frozenset({"admin", "inventory"}),
    ("GET", "/purchase-orders"): frozenset({"admin", "purchasing", "inventory", "viewer"}),
    ("POST", "/purchase-orders"): frozenset({"admin", "purchasing"}),
    ("POST", "/purchase-orders/{po_id}/submit"): frozenset({"admin", "purchasing"}),
    ("POST", "/purchase-orders/{po_id}/approve"): frozenset({"admin"}),
    ("POST", "/purchase-orders/{po_id}/receive"): frozenset({"admin", "inventory"}),
}


def test_every_registered_method_path_has_central_policy_and_golden_entry():
    # Models the owner-approved authorization contract; expected roles are handwritten, not derived from policy.py.
    registered: set[tuple[str, str]] = set()
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in route.methods or ():
            key = (method, route.path)
            registered.add(key)
            assert key in GOLDEN_ROUTE_ROLES, f"new route requires golden authorization decision: {key}"
            policy = policy_for_route(method, route.path)
            assert policy is not None
            expected_roles = GOLDEN_ROUTE_ROLES[key]
            if expected_roles is None:
                assert policy.access == "public"
                assert key in PUBLIC_ROUTE_WHITELIST
            else:
                assert policy.requires_tenant
                assert policy.roles == expected_roles
    assert registered <= set(GOLDEN_ROUTE_ROLES)


def test_metrics_is_an_explicit_allowlist_entry_but_not_a_registered_route():
    # Models the public-route inventory: metrics is reserved for internal monitoring, not public HTTP exposure.
    assert ("GET", "/metrics") in PUBLIC_ROUTE_WHITELIST
    assert not any(getattr(route, "path", None) == "/metrics" for route in app.routes)


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (
            Register,
            {
                "email": "x@example.com",
                "password": "Madar!Secure2026",
                "display_name": "X",
                "tenant_code": "x",
                "tenant_name": "X",
                "tenant_id": "evil",
            },
        ),
        (Login, {"email": "x@example.com", "password": "Madar!Secure2026", "roles": ["admin"]}),
        (InvitationIn, {"email": "x@example.com", "role": "viewer", "tenant_id": "evil"}),
        (AcceptInvitation, {"token": "x" * 20, "password": "Madar!Secure2026", "display_name": "X", "is_active": True}),
        (RefreshIn, {"refresh_token": "x" * 20, "tenant_id": "evil"}),
        (SupplierIn, {"supplier_code": "S", "legal_name": "Supplier", "status": "admin"}),
        (ProductIn, {"sku": "SKU", "name": "Product", "id": "evil"}),
        (WarehouseIn, {"code": "WH", "name": "Warehouse", "tenant_id": "evil"}),
        (AdjustIn, {"warehouse_id": "w", "product_id": "p", "quantity": "1", "tenant_id": "evil"}),
        (LineIn, {"product_id": "p", "ordered_qty": "1", "unit_price": "1", "id": "evil"}),
        (
            POIn,
            {
                "supplier_id": "s",
                "warehouse_id": "w",
                "lines": [{"product_id": "p", "ordered_qty": "1", "unit_price": "1"}],
                "status": "approved",
            },
        ),
    ],
)
def test_input_schemas_reject_mass_assignment(model, payload):
    # Models an attacker submitting server-owned fields; Pydantic must reject rather than ignore them.
    with pytest.raises(ValidationError):
        model.model_validate(payload)
