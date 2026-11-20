"""Create the initial schema with explicit DDL.

This migration intentionally mirrors the phase-0 model contract. Future schema changes
must use new revisions; it does not call Base.metadata.create_all.
"""
from alembic import op
import sqlalchemy as sa

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("tenants",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("code", sa.String(80), nullable=False), sa.Column("name", sa.String(200), nullable=False),
        sa.UniqueConstraint("code", name="uq_tenants_code"))
    op.create_index("ix_tenants_code", "tenants", ["code"], unique=True)
    op.create_table("users",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False), sa.Column("email", sa.String(255), nullable=False), sa.Column("display_name", sa.String(200), nullable=False), sa.Column("password_hash", sa.String(255), nullable=False), sa.Column("roles", sa.JSON, nullable=False), sa.UniqueConstraint("email", name="uq_users_email"))
    op.create_index("ix_users_tenant_id", "users", ["tenant_id"])
    op.create_index("ix_users_email", "users", ["email"])
    op.create_table("suppliers", sa.Column("id", sa.String(36), primary_key=True), sa.Column("tenant_id", sa.String(36), nullable=False), sa.Column("supplier_code", sa.String(80), nullable=False), sa.Column("legal_name", sa.String(200), nullable=False), sa.Column("status", sa.String(30), nullable=False), sa.Column("lead_time_days", sa.Integer, nullable=False), sa.UniqueConstraint("tenant_id", "supplier_code", name="uq_supplier_tenant_code"))
    op.create_index("ix_suppliers_tenant_id", "suppliers", ["tenant_id"])
    op.create_table("warehouses", sa.Column("id", sa.String(36), primary_key=True), sa.Column("tenant_id", sa.String(36), nullable=False), sa.Column("code", sa.String(80), nullable=False), sa.Column("name", sa.String(200), nullable=False), sa.UniqueConstraint("tenant_id", "code", name="uq_warehouse_tenant_code"))
    op.create_index("ix_warehouses_tenant_id", "warehouses", ["tenant_id"])
    op.create_table("products", sa.Column("id", sa.String(36), primary_key=True), sa.Column("tenant_id", sa.String(36), nullable=False), sa.Column("sku", sa.String(80), nullable=False), sa.Column("name", sa.String(200), nullable=False), sa.Column("unit_of_measure", sa.String(30), nullable=False), sa.Column("reorder_point", sa.Numeric(18, 4), nullable=False), sa.UniqueConstraint("tenant_id", "sku", name="uq_product_tenant_sku"))
    op.create_index("ix_products_tenant_id", "products", ["tenant_id"])
    op.create_table("inventory_balances", sa.Column("warehouse_id", sa.String(36), primary_key=True), sa.Column("product_id", sa.String(36), primary_key=True), sa.Column("tenant_id", sa.String(36), nullable=False), sa.Column("on_hand", sa.Numeric(18, 4), nullable=False), sa.Column("reserved", sa.Numeric(18, 4), nullable=False), sa.Column("on_order", sa.Numeric(18, 4), nullable=False), sa.Column("updated_at", sa.DateTime, nullable=False))
    op.create_index("ix_inventory_balances_tenant_id", "inventory_balances", ["tenant_id"])
    op.create_table("purchase_orders", sa.Column("id", sa.String(36), primary_key=True), sa.Column("tenant_id", sa.String(36), nullable=False), sa.Column("po_number", sa.String(80), nullable=False), sa.Column("supplier_id", sa.String(36), nullable=False), sa.Column("warehouse_id", sa.String(36), nullable=False), sa.Column("status", sa.String(30), nullable=False), sa.Column("currency", sa.String(3), nullable=False), sa.Column("subtotal", sa.Numeric(18, 4), nullable=False), sa.Column("tax_total", sa.Numeric(18, 4), nullable=False), sa.Column("total", sa.Numeric(18, 4), nullable=False), sa.Column("created_by", sa.String(36), nullable=False), sa.Column("created_at", sa.DateTime, nullable=False), sa.UniqueConstraint("tenant_id", "po_number", name="uq_po_tenant_number"))
    op.create_index("ix_purchase_orders_tenant_id", "purchase_orders", ["tenant_id"])
    op.create_table("purchase_order_lines", sa.Column("id", sa.String(36), primary_key=True), sa.Column("purchase_order_id", sa.String(36), sa.ForeignKey("purchase_orders.id"), nullable=False), sa.Column("product_id", sa.String(36), nullable=False), sa.Column("line_no", sa.Integer, nullable=False), sa.Column("ordered_qty", sa.Numeric(18, 4), nullable=False), sa.Column("unit_price", sa.Numeric(18, 4), nullable=False), sa.Column("tax_rate", sa.Numeric(8, 5), nullable=False))
    op.create_table("outbox_events", sa.Column("id", sa.String(36), primary_key=True), sa.Column("tenant_id", sa.String(36), nullable=False), sa.Column("event_type", sa.String(120), nullable=False), sa.Column("aggregate_id", sa.String(36), nullable=False), sa.Column("payload", sa.JSON, nullable=False), sa.Column("created_at", sa.DateTime, nullable=False))
    op.create_table("idempotency_keys", sa.Column("id", sa.String(36), primary_key=True), sa.Column("tenant_id", sa.String(36), nullable=False), sa.Column("route", sa.String(160), nullable=False), sa.Column("key", sa.String(200), nullable=False), sa.Column("request_hash", sa.String(64), nullable=False), sa.Column("response", sa.JSON), sa.Column("status", sa.String(20), nullable=False), sa.Column("created_at", sa.DateTime, nullable=False), sa.UniqueConstraint("tenant_id", "route", "key", name="uq_idem_tenant_route_key"))
    op.create_index("ix_idempotency_keys_tenant_id", "idempotency_keys", ["tenant_id"])
    op.create_table("user_invitations", sa.Column("id", sa.String(36), primary_key=True), sa.Column("tenant_id", sa.String(36), nullable=False), sa.Column("email", sa.String(255), nullable=False), sa.Column("role", sa.String(30), nullable=False), sa.Column("token_hash", sa.String(64), nullable=False), sa.Column("expires_at", sa.DateTime, nullable=False), sa.Column("used_at", sa.DateTime), sa.Column("created_at", sa.DateTime, nullable=False), sa.UniqueConstraint("token_hash"))
    op.create_index("ix_user_invitations_tenant_id", "user_invitations", ["tenant_id"])

def downgrade():
    for table in ("user_invitations", "idempotency_keys", "outbox_events", "purchase_order_lines", "purchase_orders", "inventory_balances", "products", "warehouses", "suppliers", "users", "tenants"):
        op.drop_table(table)
