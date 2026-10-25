from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    CheckConstraint,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Rating(Base):
    __tablename__ = "ratings"

    __table_args__ = (
        UniqueConstraint("order_id", name="uq_rating_order"),
        CheckConstraint(
            "restaurant_rating BETWEEN 1 AND 5",
            name="ck_restaurant_rating_range",
        ),
        CheckConstraint(
            "partner_rating BETWEEN 1 AND 5",
            name="ck_partner_rating_range",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True
    )

    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
    )

    customer_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )

    restaurant_rating: Mapped[int] = mapped_column(
        Integer, nullable=False
    )

    partner_rating: Mapped[int] = mapped_column(
        Integer, nullable=False
    )

    comment: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )