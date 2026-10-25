
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Restaurant(Base):
    __tablename__ = "restaurants"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True
    )

    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(
        String(150), nullable=False, index=True
    )

    description: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )

    address: Mapped[str] = mapped_column(
        Text, nullable=False
    )

    phone: Mapped[str] = mapped_column(
        String(20), nullable=False
    )

    cuisine_type: Mapped[str] = mapped_column(
        String(100), nullable=False
    )

    is_open: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )

    is_approved: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    # Level 4: Location-based restaurant search
    latitude: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )

    longitude: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )

    delivery_radius_km: Mapped[float] = mapped_column(
        Float, default=5.0, nullable=False
    )

    min_order_value: Mapped[float] = mapped_column(
    Float, default=0.0, nullable=False
    )

    avg_preparation_minutes: Mapped[int] = mapped_column(
        Integer, default=20, nullable=False
    )

    # Level 12: Restaurant ratings
    average_rating: Mapped[float] = mapped_column(
        Float, default=0.0, nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
