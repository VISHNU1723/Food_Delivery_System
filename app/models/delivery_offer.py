
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DeliveryOffer(Base):
    __tablename__ = "delivery_offers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    partner_id: Mapped[int] = mapped_column(
        ForeignKey("delivery_partners.id"),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        Enum(
            "Pending",
            "Accepted",
            "Declined",
            "Expired",
            name="delivery_offer_status",
        ),
        default="Pending",
        nullable=False,
    )

    offered_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False
    )
