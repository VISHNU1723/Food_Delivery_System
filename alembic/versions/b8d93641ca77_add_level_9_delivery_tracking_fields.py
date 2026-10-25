
"""add level 9 delivery tracking fields

Revision ID: b8d93641ca77
Revises: 720be7899c16
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "b8d93641ca77"
down_revision = "720be7899c16"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    inspector = inspect(connection)

    # Only add columns that do not already exist.
    existing_columns = {
        column["name"]
        for column in inspector.get_columns("orders")
    }

    if "delivery_otp_attempts" not in existing_columns:
        op.add_column(
            "orders",
            sa.Column(
                "delivery_otp_attempts",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
        )

    if "delivery_locked" not in existing_columns:
        op.add_column(
            "orders",
            sa.Column(
                "delivery_locked",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
            ),
        )

    if "assignment_started_at" not in existing_columns:
        op.add_column(
            "orders",
            sa.Column(
                "assignment_started_at",
                sa.DateTime(),
                nullable=True,
            ),
        )

    if "admin_notified_at" not in existing_columns:
        op.add_column(
            "orders",
            sa.Column(
                "admin_notified_at",
                sa.DateTime(),
                nullable=True,
            ),
        )


def downgrade():
    # Intentionally do not drop columns automatically.
    # This avoids accidental data loss.
    pass
