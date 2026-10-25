
from datetime import datetime
from decimal import Decimal, ROUND_CEILING
from math import radians, sin, cos, asin, sqrt
import secrets

from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.menu_item import MenuItem
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.restaurant import Restaurant
from app.models.user import User
from app.models.cart import Cart
from app.models.cart_item import CartItem
from app.models.address import Address
from app.models.coupon import Coupon
from app.models.coupon_usage import CouponUsage
from app.models.order_status_history import OrderStatusHistory
from app.routers.addresses import get_current_customer
from app.schemas.order import OrderCreate, OrderResponse
from app.services.delivery_assignment import assign_next_partner
from app.models.delivery_partner import DeliveryPartner
from app.schemas.deliveries import DeliveryOTPRequest
from app.services.websocket_manager import manager
from app.models.rating import Rating
from app.schemas.rating import RatingCreate, RatingResponse

router = APIRouter(prefix="/orders", tags=["Orders"])

ZERO = Decimal("0.00")
CENT = Decimal("0.01")


def money(value):
    return Decimal(str(value or 0)).quantize(CENT)


def calculate_discount(coupon: Coupon, item_total: Decimal) -> Decimal:
    if coupon.discount_type == "Percentage":
        discount = (
            item_total
            * Decimal(str(coupon.discount_value))
            / Decimal("100")
        )
        if coupon.max_discount is not None:
            discount = min(discount, Decimal(str(coupon.max_discount)))
    else:
        discount = Decimal(str(coupon.discount_value))

    return min(discount, item_total).quantize(CENT)


def validate_coupon(
    db,
    coupon,
    customer_id,
    restaurant_id,
    item_total,
):
    now = datetime.utcnow()

    if not coupon.is_active:
        raise HTTPException(400, "Coupon is inactive")

    if now < coupon.valid_from:
        raise HTTPException(400, "Coupon is not valid yet")

    if now > coupon.valid_to:
        raise HTTPException(400, "This coupon has expired")

    if (
        coupon.restaurant_id is not None
        and coupon.restaurant_id != restaurant_id
    ):
        raise HTTPException(400, "Coupon is not valid for this restaurant")

    if item_total < Decimal(str(coupon.min_order_value)):
        raise HTTPException(
            400,
            f"Minimum order value is ₹{coupon.min_order_value}",
        )

    if (
        coupon.total_usage_limit is not None
        and coupon.usage_count >= coupon.total_usage_limit
    ):
        raise HTTPException(400, "Coupon usage limit has been reached")

    usage_count = db.query(CouponUsage).filter(
        CouponUsage.coupon_id == coupon.id,
        CouponUsage.customer_id == customer_id,
    ).count()

    if usage_count >= coupon.per_user_limit:
        raise HTTPException(
            400,
            "You have reached this coupon's per-user usage limit",
        )

    if coupon.first_order_only:
        previous_delivered = db.query(Order).filter(
            Order.customer_id == customer_id,
            Order.status == "DELIVERED",
        ).first()

        if previous_delivered:
            raise HTTPException(
                400,
                "This coupon is valid only for your first order",
            )


def distance_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(
        radians,
        [float(lat1), float(lon1), float(lat2), float(lon2)],
    )

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        sin(dlat / 2) ** 2
        + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    )

    return 6371 * 2 * asin(sqrt(a))


def delivery_charge(distance):
    if distance <= 3:
        return Decimal("20.00")

    extra_km = int(
        Decimal(str(distance - 3)).to_integral_value(
            rounding=ROUND_CEILING
        )
    )

    return Decimal("20.00") + Decimal(extra_km) * Decimal("8.00")


def add_status_history(
    db,
    order,
    new_status,
    changed_by,
    old_status=None,
):
    previous_status = (
        order.status if old_status is None and order.id is not None
        else old_status
    )

    db.add(
        OrderStatusHistory(
            order_id=order.id,
            old_status=previous_status,
            new_status=new_status,
            changed_by=changed_by,
            changed_at=datetime.utcnow(),
        )
    )

    order.status = new_status


@router.get("/health")
def orders_health():
    return {"message": "Orders router is working"}


@router.post(
    "",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
def create_order(
    data: OrderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_customer),
):
    try:
        restaurant = db.query(Restaurant).filter(
            Restaurant.id == data.restaurant_id,
            Restaurant.is_open.is_(True),
            Restaurant.is_active.is_(True),
            Restaurant.is_approved.is_(True),
        ).with_for_update().first()

        if restaurant is None:
            raise HTTPException(
                404,
                "Restaurant not found or unavailable",
            )

        requested = data.items
        item_ids = [item.menu_item_id for item in requested]

        if not item_ids:
            raise HTTPException(
                400,
                "Order must contain at least one item",
            )

        if len(item_ids) != len(set(item_ids)):
            raise HTTPException(
                400,
                "Each menu item can only appear once in an order",
            )

        menu_items = db.query(MenuItem).filter(
            MenuItem.id.in_(item_ids),
            MenuItem.restaurant_id == data.restaurant_id,
        ).all()

        items_by_id = {item.id: item for item in menu_items}

        if len(items_by_id) != len(item_ids):
            raise HTTPException(
                400,
                "One or more menu items do not belong to this restaurant",
            )

        for requested_item in requested:
            menu_item = items_by_id[requested_item.menu_item_id]

            if not menu_item.is_available:
                raise HTTPException(
                    400,
                    f"Menu item '{menu_item.name}' is unavailable",
                )

        item_total = sum(
            (
                money(items_by_id[item.menu_item_id].price)
                * item.quantity
                for item in requested
            ),
            ZERO,
        ).quantize(CENT)

        minimum = money(
            getattr(restaurant, "min_order_value", 0)
        )

        if item_total < minimum:
            raise HTTPException(
                400,
                f"Minimum order value for this restaurant is ₹{minimum}",
            )

        address_id = data.address_id
        distance = 0.0

        if address_id is not None:
            saved_address = db.query(Address).filter(
                Address.id == address_id,
                Address.customer_id == current_user.id,
            ).first()

            if saved_address is None:
                raise HTTPException(400, "Saved address not found")

            if (
                restaurant.latitude is None
                or restaurant.longitude is None
            ):
                raise HTTPException(
                    400,
                    "Restaurant location is not configured",
                )

            distance = distance_km(
                restaurant.latitude,
                restaurant.longitude,
                saved_address.latitude,
                saved_address.longitude,
            )

            if distance > float(restaurant.delivery_radius_km):
                raise HTTPException(
                    400,
                    "Address is outside the restaurant's delivery radius",
                )

            delivery_address = (
                f"{saved_address.address_line}, "
                f"{saved_address.city} - {saved_address.pincode}"
            )
        else:
            # Legacy text address: distance cannot be verified.
            delivery_address = data.delivery_address

        cart = db.query(Cart).filter(
            Cart.customer_id == current_user.id
        ).with_for_update().first()

        if cart and cart.restaurant_id not in (
            None,
            data.restaurant_id,
        ):
            raise HTTPException(
                400,
                "Your cart belongs to a different restaurant",
            )

        coupon = None
        discount = ZERO

        if cart and cart.coupon_id:
            coupon = db.query(Coupon).filter(
                Coupon.id == cart.coupon_id
            ).with_for_update().first()

            if coupon is None:
                raise HTTPException(
                    400,
                    "Applied coupon no longer exists",
                )

            validate_coupon(
                db,
                coupon,
                current_user.id,
                data.restaurant_id,
                item_total,
            )

            discount = calculate_discount(coupon, item_total)

        packaging = sum(
            (
                money(
                    getattr(
                        items_by_id[item.menu_item_id],
                        "packaging_charge",
                        0,
                    )
                ) * item.quantity
                for item in requested
            ),
            ZERO,
        ).quantize(CENT)

        delivery = money(delivery_charge(distance))
        platform = Decimal("5.00")
        gst = (
            (item_total - discount) * Decimal("0.05")
        ).quantize(CENT)
        tip = money(data.tip_amount)

        grand_total = (
            item_total
            - discount
            + packaging
            + delivery
            + platform
            + gst
            + tip
        ).quantize(CENT)

        payment_method = data.payment_method
        payment_status = (
            "PAID" if payment_method == "ONLINE" else "PENDING"
        )

        order = Order(
            customer_id=current_user.id,
            restaurant_id=data.restaurant_id,
            address_id=address_id,
            status="PLACED",
            order_number=(
                f"ORD-{datetime.utcnow():%Y%m%d%H%M%S}-"
                f"{secrets.randbelow(10000):04d}"
            ),
            item_total=item_total,
            coupon_code=coupon.code if coupon else None,
            discount_amount=discount,
            packaging_charges=packaging,
            delivery_fee=delivery,
            platform_fee=platform,
            gst_amount=gst,
            tip_amount=tip,
            grand_total=grand_total,
            total_amount=grand_total,
            delivery_address=delivery_address,
            payment_method=payment_method,
            payment_status=payment_status,
            distance_km=money(distance),
            delivery_otp=f"{secrets.randbelow(10000):04d}",
            placed_at=datetime.utcnow(),
        )

        db.add(order)
        db.flush()

        # Record the initial status. There is no previous status.
        db.add(
            OrderStatusHistory(
                order_id=order.id,
                old_status=None,
                new_status="PLACED",
                changed_by=current_user.id,
                changed_at=datetime.utcnow(),
            )
        )

        for requested_item in requested:
            menu_item = items_by_id[requested_item.menu_item_id]

            db.add(
                OrderItem(
                    order_id=order.id,
                    menu_item_id=menu_item.id,
                    quantity=requested_item.quantity,
                    unit_price=menu_item.price,
                    item_name=menu_item.name,
                )
            )

        if coupon:
            db.add(
                CouponUsage(
                    coupon_id=coupon.id,
                    customer_id=current_user.id,
                    order_id=order.id,
                )
            )

            coupon.usage_count += 1
            cart.coupon_id = None

        if cart:
            cart.restaurant_id = data.restaurant_id
            db.query(CartItem).filter(
                CartItem.cart_id == cart.id
            ).delete(synchronize_session=False)

        db.commit()
        db.refresh(order)

        # Level 10: notify the owner of this restaurant about the new order.
        manager.publish_from_sync(
            manager.broadcast_restaurant(
                restaurant.owner_id,
                {
                    "event": "new_order",
                    "order_id": order.id,
                    "order_number": order.order_number,
                    "restaurant_id": restaurant.id,
                    "restaurant_name": restaurant.name,
                    "status": order.status,
                    "item_total": str(order.item_total),
                    "grand_total": str(order.grand_total),
                    "created_at": order.created_at.isoformat() if order.created_at else None,
                },
            )
        )
        return order

    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise


@router.get("", response_model=list[OrderResponse])
@router.get(
    "/",
    response_model=list[OrderResponse],
    include_in_schema=False,
)

@router.get("", response_model=list[OrderResponse])
@router.get(
    "/",
    response_model=list[OrderResponse],
    include_in_schema=False,
)
def get_my_orders(
    skip: int = 0,
    limit: int = 10,
    status_filter: str | None = None,
    restaurant_id: int | None = None,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_customer),
):
    skip = max(skip, 0)
    limit = max(1, min(limit, 100))

    query = db.query(Order).filter(
        Order.customer_id == current_user.id
    )

    if status_filter:
        query = query.filter(Order.status == status_filter.upper())

    if restaurant_id is not None:
        query = query.filter(Order.restaurant_id == restaurant_id)

    if from_date:
        query = query.filter(Order.created_at >= from_date)

    if to_date:
        query = query.filter(Order.created_at <= to_date)

    return (
        query.order_by(Order.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.get("/{order_id}", response_model=OrderResponse)
def get_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_customer),
):
    order = db.query(Order).filter(
        Order.id == order_id,
        Order.customer_id == current_user.id,
    ).first()

    if order is None:
        raise HTTPException(404, "Order not found")

    # The authenticated order owner can see their delivery OTP.
    return order


@router.put("/{order_id}/cancel")
def cancel_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_customer),
):
    order = db.query(Order).filter(
        Order.id == order_id,
        Order.customer_id == current_user.id,
    ).with_for_update().first()

    if order is None:
        raise HTTPException(404, "Order not found")

    if order.status != "PLACED":
        raise HTTPException(
            400,
            "Only placed orders can be cancelled",
        )

    try:
        old_status = order.status

        usage = db.query(CouponUsage).filter(
            CouponUsage.order_id == order.id
        ).first()

        if usage:
            coupon = db.query(Coupon).filter(
                Coupon.id == usage.coupon_id
            ).with_for_update().first()

            if coupon and coupon.usage_count > 0:
                coupon.usage_count -= 1

            db.delete(usage)

        add_status_history(
            db,
            order,
            "CANCELLED",
            current_user.id,
            old_status=old_status,
        )

        if (
            order.payment_method == "ONLINE"
            and order.payment_status == "PAID"
        ):
            # Mock refund: this updates the status; it does not call a
            # real payment provider.
            order.payment_status = "REFUNDED"

        db.commit()

        return {
            "message": "Order cancelled successfully",
            "order_id": order.id,
            "status": order.status,
            "payment_status": order.payment_status,
            "coupon_usage_released": usage is not None,
        }

    except Exception:
        db.rollback()
        raise


@router.post("/{order_id}/reorder")
def reorder(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_customer),
):
    previous = db.query(Order).filter(
        Order.id == order_id,
        Order.customer_id == current_user.id,
    ).first()

    if previous is None:
        raise HTTPException(404, "Order not found")

    old_items = db.query(OrderItem).filter(
        OrderItem.order_id == previous.id
    ).all()

    if not old_items:
        raise HTTPException(
            400,
            "This order has no items to reorder",
        )

    try:
        cart = db.query(Cart).filter(
            Cart.customer_id == current_user.id
        ).with_for_update().first()

        if cart is None:
            cart = Cart(
                customer_id=current_user.id,
                restaurant_id=previous.restaurant_id,
                coupon_id=None,
            )
            db.add(cart)
            db.flush()
        else:
            # A cart can only contain items from one restaurant.
            if cart.restaurant_id not in (
                None,
                previous.restaurant_id,
            ):
                db.query(CartItem).filter(
                    CartItem.cart_id == cart.id
                ).delete(synchronize_session=False)

            cart.restaurant_id = previous.restaurant_id
            cart.coupon_id = None

        added = []
        skipped = []

        for old_item in old_items:
            menu_item = db.query(MenuItem).filter(
                MenuItem.id == old_item.menu_item_id,
                MenuItem.restaurant_id == previous.restaurant_id,
                MenuItem.is_available.is_(True),
            ).first()

            if menu_item is None:
                skipped.append(old_item.item_name)
                continue

            cart_item = db.query(CartItem).filter(
                CartItem.cart_id == cart.id,
                CartItem.menu_item_id == menu_item.id,
            ).first()

            if cart_item:
                cart_item.quantity += old_item.quantity
                cart_item.unit_price = menu_item.price
                cart_item.item_name = menu_item.name
            else:
                db.add(
                    CartItem(
                        cart_id=cart.id,
                        menu_item_id=menu_item.id,
                        quantity=old_item.quantity,
                        unit_price=menu_item.price,
                        item_name=menu_item.name,
                    )
                )

            added.append(menu_item.name)

        db.commit()

        return {
            "message": "Reorder items copied to cart",
            "previous_order_id": previous.id,
            "added_items": added,
            "skipped_unavailable_items": skipped,
            "coupon_reapplied": False,
        }

    except Exception:
        db.rollback()
        raise



# ---------- LEVEL 8: RESTAURANT ORDER HANDLING ----------

class AcceptOrderRequest(BaseModel):
    estimated_preparation_minutes: int = Field(gt=0, le=600)


class RejectOrderRequest(BaseModel):
    rejection_reason: str = Field(min_length=3, max_length=500)


def get_restaurant_order_or_404(db, order_id, current_user):
    order = db.query(Order).filter(Order.id == order_id).first()

    if order is None:
        raise HTTPException(404, "Order not found")

    restaurant = db.query(Restaurant).filter(
        Restaurant.id == order.restaurant_id,
        Restaurant.owner_id == current_user.id,
    ).first()

    if restaurant is None:
        raise HTTPException(
            403,
            "Only the restaurant owner can manage this order",
        )

    return order, restaurant


def change_order_status(db, order, new_status, user_id):
    old_status = order.status

    add_status_history(
        db,
        order,
        new_status,
        user_id,
        old_status=old_status,
    )

    # Level 10: broadcast status changes to connected tracking clients.
    event = {
        "event": "order_status_update",
        "order_id": order.id,
        "order_number": order.order_number,
        "old_status": old_status,
        "status": new_status,
        "changed_by": user_id,
        "updated_at": datetime.utcnow().isoformat(),
    }
    manager.publish_from_sync(manager.broadcast_order(order.id, event))

    # Notify the restaurant owner and the assigned delivery partner too.
    restaurant = db.query(Restaurant).filter(
        Restaurant.id == order.restaurant_id
    ).first()
    if restaurant:
        manager.publish_from_sync(
            manager.broadcast_restaurant(
                restaurant.owner_id,
                {**event, "event": "restaurant_order_status_update"},
            )
        )

    if order.delivery_partner_id:
        manager.publish_from_sync(
            manager.broadcast_partner(
                order.delivery_partner_id,
                {**event, "event": "partner_order_status_update"},
            )
        )


@router.get("/restaurants/me/orders")
def get_restaurant_orders(
    skip: int = 0,
    limit: int = 10,
    status_filter: str | None = None,
    restaurant_id: int | None = None,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_customer),
):
    skip = max(skip, 0)
    limit = max(1, min(limit, 100))

    restaurants_query = db.query(Restaurant.id).filter(
        Restaurant.owner_id == current_user.id
    )

    if restaurant_id is not None:
        restaurants_query = restaurants_query.filter(
            Restaurant.id == restaurant_id
        )

    restaurant_ids = [row[0] for row in restaurants_query.all()]

    if not restaurant_ids:
        return []

    query = db.query(Order).filter(
        Order.restaurant_id.in_(restaurant_ids)
    )

    if status_filter:
        query = query.filter(Order.status == status_filter.upper())

    if from_date:
        query = query.filter(Order.created_at >= from_date)

    if to_date:
        query = query.filter(Order.created_at <= to_date)

    return (
        query.order_by(Order.placed_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.put("/{order_id}/accept")
def accept_order(
    order_id: int,
    data: AcceptOrderRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_customer),
):
    try:
        order, restaurant = get_restaurant_order_or_404(
            db, order_id, current_user
        )

        if order.status != "PLACED":
            raise HTTPException(
                400,
                "Only placed orders can be accepted",
            )

        # Keep the requested preparation estimate for this acceptance.
        # The restaurant model already has a default preparation estimate.
        restaurant.avg_preparation_minutes = (
            data.estimated_preparation_minutes
        )

        change_order_status(db, order, "ACCEPTED", current_user.id)

        offer = assign_next_partner(db, order)

        # Level 9 delivery-partner assignment can be triggered here.
        db.commit()

        return {
            "message": "Order accepted successfully",
            "order_id": order.id,
            "status": order.status,
            "estimated_preparation_minutes":
                data.estimated_preparation_minutes,
            "delivery_assignment": (
                "Offer sent to nearest eligible partner"
                if offer
                else "No eligible partner currently available"
            ),
            "offer_id": offer.id if offer else None,
            "offer_expires_at": offer.expires_at if offer else None,
        }

    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise


@router.put("/{order_id}/reject")
def reject_order(
    order_id: int,
    data: RejectOrderRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_customer),
):
    try:
        order, _ = get_restaurant_order_or_404(
            db, order_id, current_user
        )

        if order.status != "PLACED":
            raise HTTPException(
                400,
                "Only placed orders can be rejected",
            )

        change_order_status(db, order, "REJECTED", current_user.id)

        # Release coupon usage if the order is rejected.
        usage = db.query(CouponUsage).filter(
            CouponUsage.order_id == order.id
        ).first()

        if usage:
            coupon = db.query(Coupon).filter(
                Coupon.id == usage.coupon_id
            ).with_for_update().first()

            if coupon and coupon.usage_count > 0:
                coupon.usage_count -= 1

            db.delete(usage)

        if (
            order.payment_method == "ONLINE"
            and order.payment_status == "PAID"
        ):
            order.payment_status = "REFUNDED"

        db.commit()

        return {
            "message": "Order rejected",
            "order_id": order.id,
            "status": order.status,
            "rejection_reason": data.rejection_reason,
            "payment_status": order.payment_status,
            "coupon_usage_released": usage is not None,
        }

    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise


@router.put("/{order_id}/preparing")
def mark_order_preparing(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_customer),
):
    try:
        order, _ = get_restaurant_order_or_404(
            db, order_id, current_user
        )

        if order.status != "ACCEPTED":
            raise HTTPException(
                400,
                "Only accepted orders can move to preparing",
            )

        change_order_status(db, order, "PREPARING", current_user.id)
        db.commit()

        return {
            "message": "Order preparation started",
            "order_id": order.id,
            "status": order.status,
        }

    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise


@router.put("/{order_id}/ready")
def mark_order_ready(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_customer),
):
    try:
        order, _ = get_restaurant_order_or_404(
            db, order_id, current_user
        )

        if order.status != "PREPARING":
            raise HTTPException(
                400,
                "Only orders being prepared can be marked ready",
            )

        change_order_status(
            db, order, "READY_FOR_PICKUP", current_user.id
        )
        db.commit()

        return {
            "message": "Order is ready for pickup",
            "order_id": order.id,
            "status": order.status,
        }

    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise


def get_delivery_order_or_404(db: Session, order_id: int, current_user: User):
    order = db.query(Order).filter(Order.id == order_id).with_for_update().first()

    if order is None:
        raise HTTPException(404, "Order not found")

    if order.delivery_partner_id != current_user.id:
        raise HTTPException(403, "This order is not assigned to you")

    if order.delivery_locked:
        raise HTTPException(423, "Delivery is locked due to too many incorrect OTP attempts")

    return order


@router.put("/{order_id}/pickup")
def pickup_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_customer),
):
    order = get_delivery_order_or_404(db, order_id, current_user)

    if order.status != "READY_FOR_PICKUP":
        raise HTTPException(400, "Order must be ready for pickup")

    change_order_status(db, order, "PICKED_UP", current_user.id)
    db.commit()

    return {"message": "Order picked up", "order_id": order.id, "status": order.status}


@router.put("/{order_id}/out-for-delivery")
def mark_out_for_delivery(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_customer),
):
    order = get_delivery_order_or_404(db, order_id, current_user)

    if order.status != "PICKED_UP":
        raise HTTPException(400, "Order must be picked up first")

    change_order_status(db, order, "OUT_FOR_DELIVERY", current_user.id)
    db.commit()

    return {"message": "Order is out for delivery", "order_id": order.id, "status": order.status}


@router.put("/{order_id}/deliver")
def deliver_order(
    order_id: int,
    data: DeliveryOTPRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_customer),
):
    order = get_delivery_order_or_404(db, order_id, current_user)

    if order.status != "OUT_FOR_DELIVERY":
        raise HTTPException(400, "Order must be out for delivery")

    if str(order.delivery_otp) != data.otp:
        order.delivery_otp_attempts += 1

        if order.delivery_otp_attempts >= 3:
            order.delivery_locked = True

        db.commit()

        if order.delivery_locked:
            raise HTTPException(423, "Too many incorrect OTP attempts. Delivery locked")

        raise HTTPException(
            400,
            f"Incorrect OTP. Attempts remaining: {3 - order.delivery_otp_attempts}",
        )

    change_order_status(db, order, "DELIVERED", current_user.id)

    if order.payment_method == "COD":
        order.payment_status = "PAID"

    db.commit()

    return {
        "message": "Order delivered successfully",
        "order_id": order.id,
        "status": order.status,
        "payment_status": order.payment_status,
    }

