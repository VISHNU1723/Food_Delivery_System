
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CouponUsage(Base):
    __tablename__ = "coupon_usages"
    __table_args__ = (
        UniqueConstraint(
            "coupon_id", "order_id",
            name="uq_coupon_usage_order",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    coupon_id: Mapped[int] = mapped_column(
        ForeignKey("coupons.id"), nullable=False, index=True
    )
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id"), nullable=False, unique=True
    )
    used_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
