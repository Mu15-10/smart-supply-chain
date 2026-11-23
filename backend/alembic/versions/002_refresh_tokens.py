"""Add refresh token rotation storage."""
import sqlalchemy as sa

from alembic import op

revision = "002_refresh_tokens"
down_revision = "001_initial"
branch_labels = None
depends_on = None
def upgrade():
    op.create_table("refresh_tokens", sa.Column("id", sa.String(36), primary_key=True), sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False), sa.Column("tenant_id", sa.String(36), nullable=False), sa.Column("token_hash", sa.String(64), nullable=False), sa.Column("family_id", sa.String(36), nullable=False), sa.Column("expires_at", sa.DateTime(), nullable=False), sa.Column("revoked_at", sa.DateTime(), nullable=True), sa.Column("created_at", sa.DateTime(), nullable=False))
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_tenant_id", "refresh_tokens", ["tenant_id"])
    op.create_index("ix_refresh_tokens_family_id", "refresh_tokens", ["family_id"])
    op.create_index("ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"], unique=True)
def downgrade():
    op.drop_table("refresh_tokens")
