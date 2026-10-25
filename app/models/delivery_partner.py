
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DeliveryPartner(Base):
    __tablename__ = "delivery_partners"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        unique=True,
        nullable=False,
        index=True,
    )

    vehicle_type: Mapped[str] = mapped_column(
        Enum("Bike", "Scooter", "Bicycle", name="delivery_vehicle_type"),
        nullable=False,
    )

    vehicle_number: Mapped[str] = mapped_column(
        String(30),
        unique=True,
        nullable=False,
    )

    is_online: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    current_latitude: Mapped[float | None] = mapped_column(
        Numeric(10, 7), nullable=True
    )

    current_longitude: Mapped[float | None] = mapped_column(
        Numeric(10, 7), nullable=True
    )

    last_location_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )

    is_approved: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
