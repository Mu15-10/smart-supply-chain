"""Small, destructive-in-memory mutation audit for tenant predicates.

Each mutation is applied to a disposable working copy of main.py, the isolation tests run,
and the original source is restored in a finally block. A mutation is successful when at
least one isolation test fails; a syntax/import failure also counts as detected breakage.
"""
from __future__ import annotations

import argparse
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Mutation:
    label: str
    old: str
    new: str


MUTATIONS = (
    Mutation(
        "supplier-list-tenant-predicate",
        'select(Supplier).where(Supplier.tenant_id == c["tenant_id"])',
        "select(Supplier)",
    ),
    Mutation(
        "product-list-tenant-predicate",
        'select(Product).where(Product.tenant_id == c["tenant_id"]).order_by(Product.name)',
        "select(Product).order_by(Product.name)",
    ),
    Mutation(
        "warehouse-list-tenant-predicate",
        'select(Warehouse).where(Warehouse.tenant_id == c["tenant_id"]).order_by(Warehouse.code)',
        "select(Warehouse).order_by(Warehouse.code)",
    ),
    Mutation(
        "purchase-order-list-tenant-predicate",
        'select(PurchaseOrder)\n                    .where(PurchaseOrder.tenant_id == c["tenant_id"])',
        "select(PurchaseOrder)",
    ),
    Mutation(
        "inventory-adjust-product-tenant-predicate",
        'select(Product).where(Product.id == x.product_id, Product.tenant_id == c["tenant_id"])',
        'select(Product).where(Product.id == x.product_id)',
    ),
    Mutation(
        "inventory-adjust-warehouse-tenant-predicate",
        'p = db.scalar(select(Product).where(Product.id == x.product_id, Product.tenant_id == c["tenant_id"]))\n'
        '        w = db.scalar(select(Warehouse).where(Warehouse.id == x.warehouse_id, Warehouse.tenant_id == c["tenant_id"]))',
        'p = db.scalar(select(Product).where(Product.id == x.product_id, Product.tenant_id == c["tenant_id"]))\n'
        '        w = db.scalar(select(Warehouse).where(Warehouse.id == x.warehouse_id))',
    ),
    Mutation(
        "purchase-order-supplier-tenant-predicate",
        'select(Supplier).where(Supplier.id == x.supplier_id, Supplier.tenant_id == c["tenant_id"])',
        'select(Supplier).where(Supplier.id == x.supplier_id)',
    ),
    Mutation(
        "purchase-order-warehouse-tenant-predicate",
        's = db.scalar(select(Supplier).where(Supplier.id == x.supplier_id, Supplier.tenant_id == c["tenant_id"]))\n'
        '        w = db.scalar(select(Warehouse).where(Warehouse.id == x.warehouse_id, Warehouse.tenant_id == c["tenant_id"]))',
        's = db.scalar(select(Supplier).where(Supplier.id == x.supplier_id, Supplier.tenant_id == c["tenant_id"]))\n'
        '        w = db.scalar(select(Warehouse).where(Warehouse.id == x.warehouse_id))',
    ),
    Mutation(
        "purchase-order-transition-tenant-predicate",
        'PurchaseOrder.id == po_id, PurchaseOrder.tenant_id == c["tenant_id"]',
        "PurchaseOrder.id == po_id",
    ),
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pytest", default="tests/test_phase1c_isolation.py")
    args = parser.parse_args()
    source_path = Path(__file__).resolve().parents[1] / "backend/app/main.py"
    baseline = source_path.read_text(encoding="utf-8")
    results: list[tuple[str, str]] = []
    try:
        for mutation in MUTATIONS:
            if baseline.count(mutation.old) != 1:
                results.append((mutation.label, "NOT_APPLIED: expected one source match"))
                continue
            source_path.write_text(baseline.replace(mutation.old, mutation.new, 1), encoding="utf-8")
            completed = subprocess.run(
                ["pytest", "-q", args.pytest],
                cwd=source_path.parents[2] / "backend",
                capture_output=True,
                text=True,
                check=False,
            )
            detected = completed.returncode != 0
            results.append((mutation.label, "FAIL_DETECTED" if detected else "NOT_DETECTED"))
    finally:
        source_path.write_text(baseline, encoding="utf-8")
    print("mutation | result")
    print("--- | ---")
    for label, result in results:
        print(f"{label} | {result}")
    return 0 if all(result == "FAIL_DETECTED" for _, result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
