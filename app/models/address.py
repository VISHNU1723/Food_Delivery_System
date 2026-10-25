
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


class Address(Base):
    __tablename__ = "addresses"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True
    )
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(
        String(20), nullable=False
    )
    address_line: Mapped[str] = mapped_column(
        Text, nullable=False
    )
    city: Mapped[str] = mapped_column(
        String(100), nullable=False
    )
    pincode: Mapped[str] = mapped_column(
        String(10), nullable=False
    )
    latitude: Mapped[float] = mapped_column(
        Float, nullable=False
    )
    longitude: Mapped[float] = mapped_column(
        Float, nullable=False
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
