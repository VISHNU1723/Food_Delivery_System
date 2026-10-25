
"""add level 7 order billing fields

Revision ID: ead4fa7bd35d
Revises: af779bc13e46
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import mysql


revision = "ead4fa7bd35d"
down_revision = "af779bc13e46"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)

    # Add only columns that do not already exist.
    existing = {
        col["name"] for col in inspector.get_columns("orders")
    }

    columns = [
        ("order_number", sa.String(40), True),
        ("address_id", sa.Integer(), True),
        ("delivery_partner_id", sa.Integer(), True),
        ("item_total", sa.Numeric(10, 2), False),
        ("coupon_code", sa.String(50), True),
        ("discount_amount", sa.Numeric(10, 2), False),
        ("packaging_charges", sa.Numeric(10, 2), False),
        ("delivery_fee", sa.Numeric(10, 2), False),
        ("platform_fee", sa.Numeric(10, 2), False),
        ("gst_amount", sa.Numeric(10, 2), False),
        ("tip_amount", sa.Numeric(10, 2), False),
        ("grand_total", sa.Numeric(10, 2), False),
        (
            "payment_method",
            sa.Enum("COD", "ONLINE", name="order_payment_method"),
            True,
        ),
        ("distance_km", sa.Numeric(8, 2), False),
        ("delivery_otp", sa.String(4), True),
        ("placed_at", sa.DateTime(), True),
        ("delivered_at", sa.DateTime(), True),
    ]

    for name, col_type, nullable in columns:
        if name in existing:
            continue

        # Temporary/server defaults allow existing rows to migrate.
        kwargs = {"nullable": True}
        if name in {
            "item_total", "discount_amount", "packaging_charges",
            "delivery_fee", "platform_fee", "gst_amount",
            "tip_amount", "grand_total", "distance_km",
        }:
            kwargs["server_default"] = "0"
        elif name == "payment_method":
            kwargs["server_default"] = "COD"
        elif name == "delivery_otp":
            kwargs["server_default"] = "0000"
        elif name == "placed_at":
            kwargs["server_default"] = sa.text("CURRENT_TIMESTAMP")

        op.add_column(
            "orders",
            sa.Column(name, col_type, **kwargs),
        )

    # Populate order numbers for existing orders, then enforce uniqueness.
    conn.execute(sa.text(
        "UPDATE orders SET order_number = "
        "CONCAT('ORD-LEGACY-', id) "
        "WHERE order_number IS NULL OR order_number = ''"
    ))

    existing = {
        col["name"] for col in inspect(conn).get_columns("orders")
    }
    order_number_indexes = inspect(conn).get_indexes("orders")

    if "order_number" in existing and not any(
        idx.get("name") == "ix_orders_order_number"
        for idx in order_number_indexes
    ):
        op.create_index(
            "ix_orders_order_number",
            "orders",
            ["order_number"],
            unique=True,
        )

    # Add foreign keys only if they do not already exist.
    foreign_keys = inspect(conn).get_foreign_keys("orders")
    constrained = {
        (tuple(fk.get("constrained_columns") or []),
         fk.get("referred_table"))
        for fk in foreign_keys
    }

    if (
        (("delivery_partner_id",), "users") not in constrained
        and "delivery_partner_id" in existing
    ):
        op.create_foreign_key(
            "fk_orders_delivery_partner",
            "orders",
            "users",
            ["delivery_partner_id"],
            ["id"],
        )

    if (
        (("address_id",), "addresses") not in constrained
        and "address_id" in existing
    ):
        op.create_foreign_key(
            "fk_orders_address",
            "orders",
            "addresses",
            ["address_id"],
            ["id"],
        )

    # Extend the existing status enum without removing old values.
    op.alter_column(
        "orders",
        "status",
        existing_type=mysql.ENUM(
            "PLACED", "CONFIRMED", "PREPARING", "READY",
            "OUT_FOR_DELIVERY", "DELIVERED", "CANCELLED",
        ),
        type_=sa.Enum(
            "PLACED", "ACCEPTED", "CONFIRMED", "PREPARING",
            "READY", "READY_FOR_PICKUP", "PICKED_UP",
            "OUT_FOR_DELIVERY", "DELIVERED", "REJECTED",
            "CANCELLED", name="order_status",
        ),
        existing_nullable=False,
    )


def downgrade() -> None:
    # Intentionally do not drop columns: this migration may have
    # encountered columns that existed before it was run.
    pass
