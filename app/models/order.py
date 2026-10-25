
from datetime import datetime
from decimal import Decimal
import secrets

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def generate_order_number():
    return (
        f"ORD-{datetime.utcnow():%Y%m%d-%H%M%S}-"
        f"{secrets.randbelow(10000):04d}"
    )


def generate_delivery_otp():
    return f"{secrets.randbelow(10000):04d}"


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True
    )

    order_number: Mapped[str | None] = mapped_column(
        String(40),
        unique=True,
        index=True,
        nullable=True,
        default=generate_order_number,
    )

    customer_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )

    restaurant_id: Mapped[int] = mapped_column(
        ForeignKey("restaurants.id"), nullable=False, index=True
    )

    address_id: Mapped[int | None] = mapped_column(
        ForeignKey("addresses.id"), nullable=True
    )

    # Assigned delivery partner's user ID
    delivery_partner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )

    status: Mapped[str] = mapped_column(
        Enum(
            "PLACED",
            "ACCEPTED",
            "CONFIRMED",
            "PREPARING",
            "READY",
            "READY_FOR_PICKUP",
            "PICKED_UP",
            "OUT_FOR_DELIVERY",
            "DELIVERED",
            "REJECTED",
            "CANCELLED",
            name="order_status",
        ),
        default="PLACED",
        nullable=False,
    )

    # Level 7 billing fields
    item_total: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        default=Decimal("0.00"),
        nullable=False,
    )

    coupon_code: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )

    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        default=Decimal("0.00"),
        nullable=False,
    )

    packaging_charges: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        default=Decimal("0.00"),
        nullable=False,
    )

    delivery_fee: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        default=Decimal("20.00"),
        nullable=False,
    )

    platform_fee: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        default=Decimal("5.00"),
        nullable=False,
    )

    gst_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        default=Decimal("0.00"),
        nullable=False,
    )

    tip_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        default=Decimal("0.00"),
        nullable=False,
    )

    grand_total: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        default=Decimal("0.00"),
        nullable=False,
    )

    # Retained for existing API compatibility
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        default=Decimal("0.00"),
        nullable=False,
    )

    delivery_address: Mapped[str] = mapped_column(
        Text, nullable=False
    )

    payment_method: Mapped[str] = mapped_column(
        Enum("COD", "ONLINE", name="order_payment_method"),
        default="COD",
        nullable=False,
    )

    payment_status: Mapped[str] = mapped_column(
        Enum(
            "PENDING",
            "PAID",
            "FAILED",
            "REFUNDED",
            name="payment_status",
        ),
        default="PENDING",
        nullable=False,
    )

    # Level 9 delivery distance and customer OTP
    distance_km: Mapped[Decimal] = mapped_column(
        Numeric(8, 2),
        default=Decimal("0.00"),
        nullable=False,
    )

    delivery_otp: Mapped[str] = mapped_column(
        String(4),
        default=generate_delivery_otp,
        nullable=False,
    )

    # Level 9: OTP security
    delivery_otp_attempts: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    delivery_locked: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    # Level 9: Assignment retry tracking
    assignment_started_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    admin_notified_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    placed_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
