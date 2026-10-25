
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.order import Order
from app.models.delivery_offer import DeliveryOffer
from app.models.delivery_partner import DeliveryPartner
from app.services.delivery_assignment import retry_unassigned_orders
from app.services.websocket_manager import manager
from app.models.order_status_history import OrderStatusHistory


scheduler = AsyncIOScheduler()


def auto_reject_orders():
    db: Session = SessionLocal()
    try:
        cutoff = datetime.utcnow() - timedelta(minutes=5)

        orders = db.query(Order).filter(
            Order.status == "PLACED",
            Order.placed_at <= cutoff,
        ).all()

        for order in orders:
            old_status = order.status
            order.status = "REJECTED"

            history = OrderStatusHistory(
                order_id=order.id,
                old_status=old_status,
                new_status="REJECTED",
                changed_by=1,  # Replace 1 with a valid user ID if needed
                changed_at=datetime.utcnow(),
            )
            db.add(history)

            manager.publish_from_sync(
                manager.broadcast_order(
                    order.id,
                    {
                        "event": "order_status_update",
                        "order_id": order.id,
                        "old_status": old_status,
                        "status": "REJECTED",
                        "changed_by": "System",
                        "reason": "Restaurant did not respond",
                        "message": "Your order was rejected because the restaurant did not respond within 5 minutes.",
                    },
                )
            )

        db.commit()
    finally:
        db.close()


def expire_delivery_offers():
    db: Session = SessionLocal()
    try:
        now = datetime.utcnow()

        expired = db.query(DeliveryOffer).filter(
            DeliveryOffer.status == "Pending",
            DeliveryOffer.expires_at <= now,
        ).all()

        for offer in expired:
            offer.status = "Expired"

        db.commit()

        # Retry assignment after expiring old offers.
        retry_unassigned_orders(db)
    finally:
        db.close()


def retry_orders_and_notify_admin():
    db: Session = SessionLocal()
    try:
        results = retry_unassigned_orders(db)

        for result in results:
            if result["action"] == "admin_notification_required":
                # Send the alert to connected admin/restaurant listeners.
                manager.publish_from_sync(
                    manager.broadcast_restaurants({
                        "event": "unassigned_order_alert",
                        "order_id": result["order_id"],
                        "message": "Order has been unassigned for 15 minutes",
                    })
                )
    finally:
        db.close()


def mark_inactive_partners_offline():
    db: Session = SessionLocal()
    try:
        cutoff = datetime.utcnow() - timedelta(minutes=10)

        partners = db.query(DeliveryPartner).filter(
            DeliveryPartner.is_online.is_(True),
            DeliveryPartner.last_location_at < cutoff,
        ).all()

        for partner in partners:
            partner.is_online = False

        db.commit()
    finally:
        db.close()


def deactivate_expired_coupons():
    db: Session = SessionLocal()
    try:
        from app.models.coupon import Coupon

        now = datetime.utcnow()

        # Support either common expiry field name.
        if hasattr(Coupon, "valid_to"):
            expiry_column = Coupon.valid_to
        elif hasattr(Coupon, "expiry_date"):
            expiry_column = Coupon.expiry_date
        else:
            return

        db.query(Coupon).filter(
            expiry_column < now,
            Coupon.is_active.is_(True),
        ).update({"is_active": False}, synchronize_session=False)

        db.commit()
    finally:
        db.close()


def start_scheduler():
    if scheduler.running:
        return

    scheduler.add_job(
        auto_reject_orders,
        "interval",
        minutes=1,
        id="auto_reject_orders",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        expire_delivery_offers,
        "interval",
        seconds=10,
        id="expire_delivery_offers",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        retry_orders_and_notify_admin,
        "interval",
        minutes=1,
        id="retry_unassigned_orders",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        mark_inactive_partners_offline,
        "interval",
        minutes=5,
        id="inactive_partners",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        deactivate_expired_coupons,
        "cron",
        hour=0,
        minute=0,
        id="deactivate_expired_coupons",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    scheduler.start()
    print("Level 11 scheduled jobs started.")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
