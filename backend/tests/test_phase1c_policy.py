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


def test_every_registered_api_route_has_central_policy():
    # Models policy enforcement inventory: every registered API route must have explicit metadata.
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        policy = policy_for_route(route.path)
        assert policy is not None, route.path
        assert set(route.methods or ()) <= policy.methods | {"HEAD"}, route.path
        for method in route.methods or ():
            if policy.access == "public":
                assert (method, route.path) in PUBLIC_ROUTE_WHITELIST or method == "HEAD"
            else:
                assert policy.requires_tenant, route.path
                assert policy.roles, route.path


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
