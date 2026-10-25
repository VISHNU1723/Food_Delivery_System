
from datetime import datetime

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


class Coupon(Base):
    __tablename__ = "coupons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    code: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    discount_type: Mapped[str] = mapped_column(
        Enum("Percentage", "Flat", name="coupon_discount_type"),
        nullable=False,
    )
    discount_value: Mapped[float] = mapped_column(
        Numeric(10, 2), nullable=False
    )
    max_discount: Mapped[float | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    min_order_value: Mapped[float] = mapped_column(
        Numeric(10, 2), default=0, nullable=False
    )

    restaurant_id: Mapped[int | None] = mapped_column(
        ForeignKey("restaurants.id"), nullable=True, index=True
    )

    valid_from: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    valid_to: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    total_usage_limit: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    per_user_limit: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False
    )
    first_order_only: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    usage_count: Mapped[int] = mapped_column(
    Integer, default=0, nullable=False
    )
