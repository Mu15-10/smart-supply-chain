"""Central method/path authorization policy contracts."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from fastapi.routing import APIRoute


@dataclass(frozen=True)
class RoutePolicy:
    """Authorization contract for one normalized HTTP method and route path."""

    roles: frozenset[str]
    requires_tenant: bool
    access: str


def _policy(roles: tuple[str, ...], requires_tenant: bool, access: str) -> RoutePolicy:
    return RoutePolicy(frozenset(roles), requires_tenant, access)


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


ROUTE_POLICY_TABLE: Final[dict[tuple[str, str], RoutePolicy]] = {
    ("GET", "/health/live"): _policy((), False, "public"),
    ("GET", "/health/ready"): _policy((), False, "public"),
    ("GET", "/health"): _policy((), False, "public"),
    ("GET", "/docs"): _policy((), False, "public"),
    ("GET", "/redoc"): _policy((), False, "public"),
    ("GET", "/openapi.json"): _policy((), False, "public"),
    ("GET", "/docs/oauth2-redirect"): _policy((), False, "public"),
    ("POST", "/auth/register"): _policy((), False, "public"),
    ("POST", "/auth/login"): _policy((), False, "public"),
    ("POST", "/auth/refresh"): _policy((), False, "public"),
    ("POST", "/auth/logout"): _policy(("authenticated",), True, "write"),
    ("POST", "/auth/invitations"): _policy(("admin",), True, "write"),
    ("POST", "/auth/accept-invitation"): _policy((), False, "public"),
    ("POST", "/suppliers"): _policy(("admin", "purchasing"), True, "write"),
    ("GET", "/suppliers"): _policy(("admin", "purchasing", "inventory", "viewer"), True, "read"),
    ("POST", "/products"): _policy(("admin", "purchasing", "inventory"), True, "write"),
    ("GET", "/products"): _policy(("admin", "purchasing", "inventory", "viewer"), True, "read"),
    ("POST", "/warehouses"): _policy(("admin", "inventory"), True, "write"),
    ("GET", "/warehouses"): _policy(("admin", "purchasing", "inventory", "viewer"), True, "read"),
    ("GET", "/inventory"): _policy(("admin", "purchasing", "inventory", "viewer"), True, "read"),
    ("POST", "/inventory/adjust"): _policy(("admin", "inventory"), True, "write"),
    ("POST", "/purchase-orders"): _policy(("admin", "purchasing"), True, "write"),
    ("GET", "/purchase-orders"): _policy(("admin", "purchasing", "inventory", "viewer"), True, "read"),
    ("POST", "/purchase-orders/{po_id}/submit"): _policy(("admin", "purchasing"), True, "write"),
    ("POST", "/purchase-orders/{po_id}/approve"): _policy(("admin",), True, "write"),
    ("POST", "/purchase-orders/{po_id}/receive"): _policy(("admin", "inventory"), True, "write"),
}


def policy_for_route(method: str, path: str) -> RoutePolicy | None:
    """Return the exact policy for an HTTP method and FastAPI route path."""

    return ROUTE_POLICY_TABLE.get((method.upper(), path))


def validate_route_policy_table(routes: Sequence[object]) -> None:
    """Fail closed when a registered HTTP method/path has no central policy."""

    missing: list[str] = []
    for route in routes:
        if not isinstance(route, APIRoute):
            continue
        for method in route.methods or ():
            if policy_for_route(method, route.path) is None:
                missing.append(f"{method} {route.path}")
    if missing:
        raise RuntimeError(f"Routes missing central policy: {', '.join(sorted(set(missing)))}")
