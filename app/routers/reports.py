
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database import get_db
from app.models.order import Order
from app.models.payment import Payment
from app.models.restaurant import Restaurant
from app.models.coupon import Coupon
from app.models.user import User
from app.routers.addresses import get_current_customer
from app.models.order_item import OrderItem
from app.models.menu_item import MenuItem

router = APIRouter(prefix="/reports", tags=["Reports"])


def require_role(user: User, *roles: str):
    if user.role not in roles:
        raise HTTPException(
            status_code=403,
            detail="Insufficient permissions",
        )


def date_range(start_date: date, end_date: date):
    if end_date < start_date:
        raise HTTPException(
            status_code=400,
            detail="end_date must be on or after start_date",
        )

    start = datetime.combine(start_date, time.min)
    end = datetime.combine(end_date + timedelta(days=1), time.min)
    return start, end


def order_revenue_expression():
    return func.coalesce(
        func.sum(Order.grand_total),
        0,
    )


# 1. Admin dashboard
@router.get("/admin-dashboard")
def admin_dashboard(
    report_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_customer),
):
    require_role(current_user, "ADMIN")

    today = report_date or date.today()
    start, end = date_range(today, today)

    orders = db.query(Order).filter(
        Order.created_at >= start,
        Order.created_at < end,
    )

    total_orders = orders.count()

    delivered_orders = orders.filter(
        Order.status == "DELIVERED"
    ).count()

    cancelled_orders = orders.filter(
        Order.status == "CANCELLED"
    ).count()

    rejected_orders = orders.filter(
        Order.status == "REJECTED"
    ).count()

    revenue = db.query(
        func.coalesce(func.sum(Order.grand_total), 0)
    ).filter(
        Order.created_at >= start,
        Order.created_at < end,
        Order.status == "DELIVERED",
        Order.payment_status.in_(["PAID", "PENDING"]),
    ).scalar()

    discount = db.query(
        func.coalesce(func.sum(Order.discount_amount), 0)
    ).filter(
        Order.created_at >= start,
        Order.created_at < end,
    ).scalar()

    online_partners = db.query(User).filter(
        User.role == "DELIVERY_PARTNER",
        User.is_active.is_(True),
    ).count()

    delivery_seconds = db.query(
        text("AVG(TIMESTAMPDIFF(SECOND, placed_at, delivered_at))")
    ).select_from(Order).filter(
        Order.created_at >= start,
        Order.created_at < end,
        Order.status == "DELIVERED",
        Order.delivered_at.isnot(None),
    ).scalar()

    return {
        "date": today.isoformat(),
        "total_orders": total_orders,
        "delivered_orders": delivered_orders,
        "cancelled_orders": cancelled_orders,
        "rejected_orders": rejected_orders,
        "total_revenue": float(revenue or 0),
        "total_discount_given": float(discount or 0),
        "online_partners": online_partners,
        "average_delivery_minutes": round(
            float(delivery_seconds or 0) / 60, 2
        ),
    }


# 2. Top 10 restaurants by orders and revenue
@router.get("/top-restaurants")
def top_restaurants(
    start_date: date = Query(...),
    end_date: date = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_customer),
):
    require_role(current_user, "ADMIN")
    start, end = date_range(start_date, end_date)

    rows = (
        db.query(
            Restaurant.id.label("restaurant_id"),
            Restaurant.name.label("restaurant_name"),
            func.count(Order.id).label("total_orders"),
            func.coalesce(func.sum(Order.grand_total), 0).label("revenue"),
        )
        .join(Order, Order.restaurant_id == Restaurant.id)
        .filter(
            Order.created_at >= start,
            Order.created_at < end,
            Order.status == "DELIVERED",
        )
        .group_by(Restaurant.id, Restaurant.name)
        .order_by(
            func.sum(Order.grand_total).desc(),
            func.count(Order.id).desc(),
        )
        .limit(10)
        .all()
    )

    return [
        {
            "restaurant_id": row.restaurant_id,
            "restaurant_name": row.restaurant_name,
            "total_orders": row.total_orders,
            "revenue": float(row.revenue or 0),
        }
        for row in rows
    ]


# 3. Coupon usage report
@router.get("/coupon-usage")
def coupon_usage(
    start_date: date = Query(...),
    end_date: date = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_customer),
):
    require_role(current_user, "ADMIN", "RESTAURANT_OWNER")
    start, end = date_range(start_date, end_date)

    query = (
        db.query(
            Coupon.id.label("coupon_id"),
            Coupon.code.label("coupon_code"),
            Coupon.restaurant_id.label("restaurant_id"),
            func.count(Order.id).label("times_used"),
            func.coalesce(func.sum(Order.discount_amount), 0).label(
                "total_discount_given"
            ),
            func.coalesce(func.sum(Order.grand_total), 0).label(
                "revenue"
            ),
        )
        .outerjoin(
            Order,
            (Order.coupon_code == Coupon.code)
            & (Order.created_at >= start)
            & (Order.created_at < end)
            & (Order.status == "DELIVERED"),
        )
    )

    if current_user.role == "RESTAURANT_OWNER":
        owned_restaurants = db.query(Restaurant.id).filter(
            Restaurant.owner_id == current_user.id
        )
        query = query.filter(
            Coupon.restaurant_id.in_(owned_restaurants)
        )

    rows = query.group_by(
        Coupon.id,
        Coupon.code,
        Coupon.restaurant_id,
    ).order_by(
        func.count(Order.id).desc()
    ).all()

    return [
        {
            "coupon_id": row.coupon_id,
            "coupon_code": row.coupon_code,
            "restaurant_id": row.restaurant_id,
            "times_used": row.times_used,
            "total_discount_given": float(
                row.total_discount_given or 0
            ),
            "revenue": float(row.revenue or 0),
        }
        for row in rows
    ]


# 4. Restaurant sales report
@router.get("/restaurant-sales")
def restaurant_sales(
    start_date: date = Query(...),
    end_date: date = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_customer),
):
    require_role(current_user, "RESTAURANT_OWNER")
    start, end = date_range(start_date, end_date)

    restaurants = db.query(Restaurant).filter(
        Restaurant.owner_id == current_user.id
    ).all()

    if not restaurants:
        return []

    report = []

    for restaurant in restaurants:
        daily_rows = (
            db.query(
                func.date(Order.created_at).label("day"),
                func.count(Order.id).label("total_orders"),
                func.coalesce(
                    func.sum(Order.grand_total), 0
                ).label("sales"),
            )
            .filter(
                Order.restaurant_id == restaurant.id,
                Order.created_at >= start,
                Order.created_at < end,
                Order.status == "DELIVERED",
            )
            .group_by(func.date(Order.created_at))
            .order_by(func.date(Order.created_at))
            .all()
        )

        best_sellers = (
            db.query(
                OrderItem.item_name.label("item_name"),
                func.sum(OrderItem.quantity).label("quantity_sold"),
                func.sum(
                    OrderItem.quantity * OrderItem.unit_price
                ).label("sales"),
            )
            .join(Order, Order.id == OrderItem.order_id)
            .filter(
                Order.restaurant_id == restaurant.id,
                Order.created_at >= start,
                Order.created_at < end,
                Order.status == "DELIVERED",
            )
            .group_by(OrderItem.item_name)
            .order_by(func.sum(OrderItem.quantity).desc())
            .limit(5)
            .all()
        )

        report.append({
            "restaurant_id": restaurant.id,
            "restaurant_name": restaurant.name,
            "daily_sales": [
                {
                    "date": str(row.day),
                    "total_orders": row.total_orders,
                    "sales": float(row.sales or 0),
                }
                for row in daily_rows
            ],
            "total_orders": sum(
                row.total_orders for row in daily_rows
            ),
            "total_sales": sum(
                float(row.sales or 0) for row in daily_rows
            ),
            "best_selling_items": [
                {
                    "item_name": row.item_name,
                    "quantity_sold": int(row.quantity_sold or 0),
                    "sales": float(row.sales or 0),
                }
                for row in best_sellers
            ],
        })

    return report


# 5. Delivery partner summary
@router.get("/partner-summary")
def partner_summary(
    start_date: date = Query(...),
    end_date: date = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_customer),
):
    require_role(current_user, "DELIVERY_PARTNER")
    start, end = date_range(start_date, end_date)

    rows = (
        db.query(
            func.date(Order.delivered_at).label("day"),
            func.count(Order.id).label("deliveries_completed"),
            func.coalesce(func.sum(Order.distance_km), 0).label(
                "total_distance_km"
            ),
        )
        .filter(
            Order.delivery_partner_id == current_user.id,
            Order.status == "DELIVERED",
            Order.delivered_at >= start,
            Order.delivered_at < end,
        )
        .group_by(func.date(Order.delivered_at))
        .order_by(func.date(Order.delivered_at))
        .all()
    )

    earnings_rows = (
        db.query(
            func.date(Payment.created_at).label("day"),
            func.coalesce(func.sum(Payment.amount), 0).label("earnings"),
        )
        .join(Order, Payment.order_id == Order.id)
        .filter(
            Order.delivery_partner_id == current_user.id,
            Order.status == "DELIVERED",
            Payment.status == "SUCCESS",
            Payment.created_at >= start,
            Payment.created_at < end,
        )
        .group_by(func.date(Payment.created_at))
        .all()
    )

    earnings_by_day = {
        str(row.day): float(row.earnings or 0)
        for row in earnings_rows
    }

    return [
        {
            "date": str(row.day),
            "deliveries_completed": row.deliveries_completed,
            "total_distance_km": float(row.total_distance_km or 0),
            "earnings": earnings_by_day.get(str(row.day), 0),
        }
        for row in rows
    ]
