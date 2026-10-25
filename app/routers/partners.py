
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.routers.auth import get_current_user
from app.models.user import User
from app.models.order import Order
from app.models.delivery_partner import DeliveryPartner
from app.models.delivery_offer import DeliveryOffer

router = APIRouter(tags=["Delivery Partners"])


def require_partner(db: Session, user: User) -> DeliveryPartner:
    if user.role != "DELIVERY_PARTNER":
        raise HTTPException(status_code=403, detail="Delivery partner role required")

    partner = db.query(DeliveryPartner).filter(
        DeliveryPartner.user_id == user.id
    ).first()

    if not partner:
        raise HTTPException(
            status_code=404,
            detail="Delivery partner profile not found. Contact an administrator.",
        )

    if not partner.is_approved:
        raise HTTPException(status_code=403, detail="Partner account is not approved")

    return partner


class AvailabilityUpdate(BaseModel):
    is_online: bool


class LocationUpdate(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


@router.put("/partners/me/availability")
def update_availability(
    payload: AvailabilityUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    partner = require_partner(db, user)
    partner.is_online = payload.is_online
    partner.updated_at = datetime.utcnow()
    db.commit()

    return {
        "message": "Availability updated",
        "is_online": partner.is_online,
    }


@router.put("/partners/me/location")
def update_location(
    payload: LocationUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    partner = require_partner(db, user)
    partner.current_latitude = payload.latitude
    partner.current_longitude = payload.longitude
    partner.last_location_at = datetime.utcnow()
    partner.updated_at = datetime.utcnow()
    db.commit()

    return {
        "message": "Location updated",
        "latitude": float(partner.current_latitude),
        "longitude": float(partner.current_longitude),
        "last_location_at": partner.last_location_at,
    }


@router.get("/partners/me/offers")
def get_my_offers(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    partner = require_partner(db, user)
    now = datetime.utcnow()

    # Mark expired pending offers as expired.
    expired = db.query(DeliveryOffer).filter(
        DeliveryOffer.partner_id == partner.id,
        DeliveryOffer.status == "Pending",
        DeliveryOffer.expires_at <= now,
    ).all()

    for offer in expired:
        offer.status = "Expired"

    db.commit()

    offers = (
        db.query(DeliveryOffer)
        .filter(
            DeliveryOffer.partner_id == partner.id,
            DeliveryOffer.status == "Pending",
            DeliveryOffer.expires_at > now,
        )
        .order_by(DeliveryOffer.offered_at.desc())
        .all()
    )

    return [
        {
            "offer_id": offer.id,
            "order_id": offer.order_id,
            "status": offer.status,
            "offered_at": offer.offered_at,
            "expires_at": offer.expires_at,
        }
        for offer in offers
    ]


@router.put("/offers/{offer_id}/accept")
def accept_offer(
    offer_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    partner = require_partner(db, user)

    if not partner.is_online:
        raise HTTPException(status_code=400, detail="Go online before accepting offers")

    now = datetime.utcnow()

    offer = (
        db.query(DeliveryOffer)
        .filter(DeliveryOffer.id == offer_id)
        .with_for_update()
        .first()
    )

    if not offer or offer.partner_id != partner.id:
        raise HTTPException(status_code=404, detail="Offer not found")

    if offer.status != "Pending":
        raise HTTPException(status_code=400, detail="Offer is no longer pending")

    if offer.expires_at <= now:
        offer.status = "Expired"
        db.commit()
        raise HTTPException(status_code=400, detail="Offer has expired")

    order = (
        db.query(Order)
        .filter(Order.id == offer.order_id)
        .with_for_update()
        .first()
    )

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.delivery_partner_id is not None:
        offer.status = "Expired"
        db.commit()
        raise HTTPException(status_code=409, detail="Order already has a delivery partner")

    active_statuses = [
        "ACCEPTED",
        "CONFIRMED",
        "PREPARING",
        "READY",
        "READY_FOR_PICKUP",
        "PICKED_UP",
        "OUT_FOR_DELIVERY",
    ]

    active_order = db.query(Order).filter(
        Order.delivery_partner_id == user.id,
        Order.status.in_(active_statuses),
    ).first()

    if active_order:
        raise HTTPException(
            status_code=409,
            detail="You already have an active delivery",
        )

    order.delivery_partner_id = user.id
    offer.status = "Accepted"

    # Other pending offers for this order are no longer valid.
    other_offers = db.query(DeliveryOffer).filter(
        DeliveryOffer.order_id == order.id,
        DeliveryOffer.id != offer.id,
        DeliveryOffer.status == "Pending",
    ).all()

    for other in other_offers:
        other.status = "Expired"

    db.commit()

    return {
        "message": "Delivery offer accepted",
        "offer_id": offer.id,
        "order_id": order.id,
        "delivery_partner_id": user.id,
    }


@router.put("/offers/{offer_id}/decline")
def decline_offer(
    offer_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    partner = require_partner(db, user)

    offer = db.query(DeliveryOffer).filter(
        DeliveryOffer.id == offer_id
    ).with_for_update().first()

    if not offer or offer.partner_id != partner.id:
        raise HTTPException(status_code=404, detail="Offer not found")

    if offer.status != "Pending":
        raise HTTPException(status_code=400, detail="Offer is no longer pending")

    offer.status = "Declined"
    db.commit()

    return {
        "message": "Offer declined",
        "offer_id": offer.id,
        "order_id": offer.order_id,
        "status": offer.status,
    }


@router.get("/partners/me/earnings")
def get_earnings(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    partner = require_partner(db, user)

    if start_date and end_date and start_date > end_date:
        raise HTTPException(
            status_code=400,
            detail="start_date must be on or before end_date",
        )

    today = date.today()
    today_start = datetime.combine(today, datetime.min.time())
    tomorrow_start = today_start + timedelta(days=1)

    query = db.query(Order).filter(
        Order.delivery_partner_id == user.id,
        Order.status == "DELIVERED",
        Order.delivered_at.isnot(None),
    )

    today_orders = query.filter(
        Order.delivered_at >= today_start,
        Order.delivered_at < tomorrow_start,
    ).all()

    if start_date:
        query = query.filter(
            Order.delivered_at >= datetime.combine(
                start_date, datetime.min.time()
            )
        )

    if end_date:
        query = query.filter(
            Order.delivered_at < datetime.combine(
                end_date + timedelta(days=1), datetime.min.time()
            )
        )

    deliveries = query.order_by(Order.delivered_at.desc()).all()

    def calculate(order: Order) -> float:
        distance = float(order.distance_km or 0)
        tip = float(order.tip_amount or 0)
        return round(25 + (6 * distance) + tip, 2)

    return {
        "today": {
            "deliveries": len(today_orders),
            "earnings": round(sum(calculate(o) for o in today_orders), 2),
        },
        "date_range": {
            "start_date": start_date,
            "end_date": end_date,
            "deliveries": len(deliveries),
            "earnings": round(sum(calculate(o) for o in deliveries), 2),
        },
        "delivery_details": [
            {
                "order_id": order.id,
                "delivered_at": order.delivered_at,
                "distance_km": float(order.distance_km or 0),
                "tip_amount": float(order.tip_amount or 0),
                "earning": calculate(order),
            }
            for order in deliveries
        ],
    }
