"""Central route authorization policy metadata for tenant isolation tests."""

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class RoutePolicy:
    """Authorization contract for one normalized FastAPI route path."""

    methods: frozenset[str]
    roles: frozenset[str]
    requires_tenant: bool
    access: str


PUBLIC_ROUTE_WHITELIST: Final[frozenset[tuple[str, str]]] = frozenset(
    {
        ("GET", "/health/live"),
        ("GET", "/health/ready"),
        ("GET", "/health"),
        ("GET", "/metrics"),  # Reserved explicit allow-list entry; endpoint is not registered.
        ("GET", "/docs"),
        ("GET", "/redoc"),
        ("GET", "/openapi.json"),
        ("GET", "/docs/oauth2-redirect"),
        ("POST", "/auth/register"),
        ("POST", "/auth/login"),
        ("POST", "/auth/refresh"),
        ("POST", "/auth/accept-invitation"),
    }
)


def _policy(
    methods: tuple[str, ...],
    roles: tuple[str, ...],
    requires_tenant: bool,
    access: str,
) -> RoutePolicy:
    return RoutePolicy(frozenset(methods), frozenset(roles), requires_tenant, access)


ROUTE_POLICY_TABLE: Final[dict[str, RoutePolicy]] = {
    "/health/live": _policy(("GET",), (), False, "public"),
    "/health/ready": _policy(("GET",), (), False, "public"),
    "/health": _policy(("GET",), (), False, "public"),
    "/docs": _policy(("GET",), (), False, "public"),
    "/redoc": _policy(("GET",), (), False, "public"),
    "/openapi.json": _policy(("GET",), (), False, "public"),
    "/docs/oauth2-redirect": _policy(("GET",), (), False, "public"),
    "/auth/register": _policy(("POST",), (), False, "public"),
    "/auth/login": _policy(("POST",), (), False, "public"),
    "/auth/refresh": _policy(("POST",), (), False, "public"),
    "/auth/logout": _policy(("POST",), ("authenticated",), True, "write"),
    "/auth/invitations": _policy(("POST",), ("admin",), True, "write"),
    "/auth/accept-invitation": _policy(("POST",), (), False, "public"),
    "/suppliers": _policy(("GET", "POST"), ("authenticated", "admin", "purchasing"), True, "read/write"),
    "/products": _policy(("GET", "POST"), ("authenticated", "admin", "purchasing", "inventory"), True, "read/write"),
    "/warehouses": _policy(("GET", "POST"), ("authenticated", "admin", "inventory"), True, "read/write"),
    "/inventory": _policy(("GET",), ("authenticated",), True, "read"),
    "/inventory/adjust": _policy(("POST",), ("admin", "inventory"), True, "write"),
    "/purchase-orders": _policy(("GET", "POST"), ("authenticated", "admin", "purchasing"), True, "read/write"),
    "/purchase-orders/{po_id}/submit": _policy(("POST",), ("admin", "purchasing"), True, "write"),
    "/purchase-orders/{po_id}/approve": _policy(("POST",), ("admin",), True, "write"),
    "/purchase-orders/{po_id}/receive": _policy(("POST",), ("admin", "inventory"), True, "write"),
}


def policy_for_route(path: str) -> RoutePolicy | None:
    """Return the exact policy for a FastAPI route path, if declared."""

    return ROUTE_POLICY_TABLE.get(path)
