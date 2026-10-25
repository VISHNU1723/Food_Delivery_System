
"""add order status history

Revision ID: c01f08a88414
Revises: 6265dcdd357d
"""
from alembic import op
import sqlalchemy as sa

revision = "c01f08a88414"
down_revision = "6265dcdd357d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "order_status_history",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "order_id",
            sa.Integer(),
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("old_status", sa.String(50), nullable=True),
        sa.Column("new_status", sa.String(50), nullable=False),
        sa.Column("changed_by", sa.Integer(), nullable=False),
        sa.Column(
            "changed_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index(
        "ix_order_status_history_order_id",
        "order_status_history",
        ["order_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_order_status_history_order_id",
        table_name="order_status_history",
    )
    op.drop_table("order_status_history")
