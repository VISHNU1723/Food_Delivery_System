
from datetime import datetime, timedelta
from math import radians, sin, cos, asin, sqrt

from sqlalchemy.orm import Session

from app.models.order import Order
from app.models.restaurant import Restaurant
from app.models.delivery_partner import DeliveryPartner
from app.models.delivery_offer import DeliveryOffer
from app.services.websocket_manager import manager


ACTIVE_STATUSES = [
    "ACCEPTED",
    "CONFIRMED",
    "PREPARING",
    "READY",
    "READY_FOR_PICKUP",
    "PICKED_UP",
    "OUT_FOR_DELIVERY",
]


def distance_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(
        radians, [float(lat1), float(lon1), float(lat2), float(lon2)]
    )
    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        sin(dlat / 2) ** 2
        + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    )
    return 6371 * 2 * asin(sqrt(a))


def assign_next_partner(db: Session, order: Order):
    """Offer an unassigned order to the nearest eligible partner."""

    if order.delivery_partner_id is not None:
        return None

    restaurant = db.query(Restaurant).filter(
        Restaurant.id == order.restaurant_id
    ).first()

    if (
        restaurant is None
        or restaurant.latitude is None
        or restaurant.longitude is None
    ):
        return None

    already_tried = {
        row.partner_id
        for row in db.query(DeliveryOffer.partner_id).filter(
            DeliveryOffer.order_id == order.id
        ).all()
    }

    partners = db.query(DeliveryPartner).filter(
        DeliveryPartner.is_approved.is_(True),
        DeliveryPartner.is_online.is_(True),
        DeliveryPartner.current_latitude.isnot(None),
        DeliveryPartner.current_longitude.isnot(None),
    ).all()

    candidates = []

    for partner in partners:
        if partner.id in already_tried:
            continue

        busy = db.query(Order.id).filter(
            Order.delivery_partner_id == partner.user_id,
            Order.status.in_(ACTIVE_STATUSES),
        ).first()

        if busy:
            continue

        pickup_distance = distance_km(
            restaurant.latitude,
            restaurant.longitude,
            partner.current_latitude,
            partner.current_longitude,
        )

        if pickup_distance <= 5:
            candidates.append((pickup_distance, partner))

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0])
    pickup_distance, nearest = candidates[0]
    now = datetime.utcnow()
    expires_at = now + timedelta(seconds=30)

    offer = DeliveryOffer(
        order_id=order.id,
        partner_id=nearest.id,
        status="Pending",
        offered_at=now,
        expires_at=expires_at,
    )

    db.add(offer)

    if getattr(order, "assignment_started_at", None) is None:
        order.assignment_started_at = now

    db.flush()

    # Send the offer to the selected partner's WebSocket connection.
    # partner.user_id is the User ID used by /ws/partner.
    remaining_seconds = max(
        0, int((expires_at - datetime.utcnow()).total_seconds())
    )

    notification = {
        "event": "delivery_offer",
        "offer_id": offer.id,
        "order_id": order.id,
        "order_number": order.order_number,
        "restaurant_name": restaurant.name,
        "pickup_distance_km": round(float(pickup_distance), 2),
        "delivery_distance_km": float(order.distance_km or 0),
        "expected_earnings": float(order.delivery_fee or 0),
        "seconds_left": remaining_seconds,
        "expires_at": expires_at.isoformat(),
    }

    manager.publish_from_sync(
        manager.broadcast_partner(nearest.user_id, notification)
    )

    return offer


def retry_unassigned_orders(db: Session):
    """Retry unassigned orders and flag those waiting 15 minutes."""

    now = datetime.utcnow()

    orders = db.query(Order).filter(
        Order.status.in_(ACTIVE_STATUSES),
        Order.delivery_partner_id.is_(None),
        Order.assignment_started_at.isnot(None),
    ).all()

    results = []

    for order in orders:
        started_at = order.assignment_started_at

        if (
            now >= started_at + timedelta(minutes=15)
            and order.admin_notified_at is None
        ):
            order.admin_notified_at = now
            results.append({
                "order_id": order.id,
                "action": "admin_notification_required",
            })

        latest_offer = db.query(DeliveryOffer).filter(
            DeliveryOffer.order_id == order.id,
        ).order_by(DeliveryOffer.offered_at.desc()).first()

        if latest_offer and latest_offer.status == "Pending":
            if latest_offer.expires_at > now:
                continue
            latest_offer.status = "Expired"

        if latest_offer and latest_offer.status == "Accepted":
            continue

        last_attempt = (
            latest_offer.offered_at if latest_offer else started_at
        )

        if now < last_attempt + timedelta(minutes=1):
            continue

        offer = assign_next_partner(db, order)

        results.append({
            "order_id": order.id,
            "action": "offer_created" if offer else "no_eligible_partner",
            "offer_id": offer.id if offer else None,
        })

    db.commit()
    return results
