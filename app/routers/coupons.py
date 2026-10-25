
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.coupon import Coupon
from app.models.restaurant import Restaurant
from app.models.user import User
from app.routers.addresses import get_current_customer
from app.schemas.coupon import CouponCreate, CouponUpdate, CouponResponse

router = APIRouter(prefix="/coupons", tags=["Coupons"])


def require_admin_or_owner(user: User):
    if user.role not in ("ADMIN", "RESTAURANT_OWNER"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")


def check_restaurant_permission(
    db: Session,
    user: User,
    restaurant_id: int | None,
):
    if restaurant_id is None:
        if user.role != "ADMIN":
            raise HTTPException(
                status_code=403,
                detail="Only admins can create platform-wide coupons",
            )
        return

    restaurant = db.query(Restaurant).filter(
        Restaurant.id == restaurant_id
    ).first()

    if restaurant is None:
        raise HTTPException(status_code=404, detail="Restaurant not found")

    if user.role == "RESTAURANT_OWNER" and restaurant.owner_id != user.id:
        raise HTTPException(
            status_code=403,
            detail="You can only manage coupons for your own restaurants",
        )


def normalize_code(code: str) -> str:
    return code.strip().upper()


def validate_coupon_values(
    discount_type: str,
    discount_value: float,
    valid_from: datetime,
    valid_to: datetime,
    max_discount: float | None,
):
    if valid_to <= valid_from:
        raise HTTPException(status_code=400, detail="valid_to must be after valid_from")

    if discount_value <= 0:
        raise HTTPException(status_code=400, detail="discount_value must be greater than zero")

    if discount_type == "Percentage" and not 1 <= discount_value <= 100:
        raise HTTPException(
            status_code=400,
            detail="Percentage discount must be between 1 and 100",
        )

    if discount_type == "Flat" and max_discount is not None:
        raise HTTPException(
            status_code=400,
            detail="max_discount is only valid for Percentage coupons",
        )


@router.post("", response_model=CouponResponse, status_code=201)
@router.post("/", response_model=CouponResponse, status_code=201, include_in_schema=False)
def create_coupon(
    data: CouponCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_customer),
):
    require_admin_or_owner(current_user)
    check_restaurant_permission(db, current_user, data.restaurant_id)

    code = normalize_code(data.code)

    if db.query(Coupon).filter(Coupon.code == code).first():
        raise HTTPException(status_code=409, detail="Coupon code already exists")

    coupon_data = data.model_dump()
    coupon_data["code"] = code

    coupon = Coupon(
        **coupon_data,
        created_by=current_user.id,
        usage_count=0,
    )
    db.add(coupon)

    try:
        db.commit()
        db.refresh(coupon)
        return coupon
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Coupon code already exists or violates a database constraint",
        )
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Unable to create coupon due to a database error")


@router.get("", response_model=list[CouponResponse])
@router.get("/", response_model=list[CouponResponse], include_in_schema=False)
def get_coupons(
    restaurant_id: int | None = Query(default=None, gt=0),
    is_active: bool | None = None,
    discount_type: str | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_customer),
):
    require_admin_or_owner(current_user)

    query = db.query(Coupon)

    if current_user.role == "RESTAURANT_OWNER":
        owned_restaurants = db.query(Restaurant.id).filter(
            Restaurant.owner_id == current_user.id
        )
        query = query.filter(
            (Coupon.restaurant_id.is_(None))
            | (Coupon.restaurant_id.in_(owned_restaurants))
        )

    if restaurant_id is not None:
        query = query.filter(Coupon.restaurant_id == restaurant_id)

    if is_active is not None:
        query = query.filter(Coupon.is_active == is_active)

    if discount_type is not None:
        query = query.filter(Coupon.discount_type == discount_type)

    return query.order_by(Coupon.id.desc()).offset(skip).limit(limit).all()


@router.put("/{coupon_id}", response_model=CouponResponse)
def update_coupon(
    coupon_id: int,
    data: CouponUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_customer),
):
    require_admin_or_owner(current_user)

    coupon = db.query(Coupon).filter(Coupon.id == coupon_id).first()
    if coupon is None:
        raise HTTPException(status_code=404, detail="Coupon not found")

    check_restaurant_permission(db, current_user, coupon.restaurant_id)
    updates = data.model_dump(exclude_unset=True)

    if "code" in updates:
        raise HTTPException(status_code=400, detail="Coupon code cannot be changed")

    if "restaurant_id" in updates:
        check_restaurant_permission(db, current_user, updates["restaurant_id"])

    validate_coupon_values(
        updates.get("discount_type", coupon.discount_type),
        float(updates.get("discount_value", coupon.discount_value)),
        updates.get("valid_from", coupon.valid_from),
        updates.get("valid_to", coupon.valid_to),
        (
            float(updates.get("max_discount", coupon.max_discount))
            if updates.get("max_discount", coupon.max_discount) is not None
            else None
        ),
    )

    for key, value in updates.items():
        setattr(coupon, key, value)

    try:
        db.commit()
        db.refresh(coupon)
        return coupon
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Coupon update conflicts with a database constraint")
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Unable to update coupon due to a database error")


@router.put("/{coupon_id}/deactivate", response_model=CouponResponse)
def deactivate_coupon(
    coupon_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_customer),
):
    require_admin_or_owner(current_user)

    coupon = db.query(Coupon).filter(Coupon.id == coupon_id).first()
    if coupon is None:
        raise HTTPException(status_code=404, detail="Coupon not found")

    check_restaurant_permission(db, current_user, coupon.restaurant_id)
    coupon.is_active = False

    try:
        db.commit()
        db.refresh(coupon)
        return coupon
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Unable to deactivate coupon due to a database error")


@router.get("/available")
def get_available_coupons(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_customer),
):
    from app.models.cart import Cart
    from app.models.cart_item import CartItem

    cart = db.query(Cart).filter(Cart.customer_id == current_user.id).first()

    if not cart or not cart.restaurant_id:
        return []

    items = db.query(CartItem).filter(CartItem.cart_id == cart.id).all()
    if not items:
        return []

    item_total = sum(
        (Decimal(str(item.unit_price)) * item.quantity for item in items),
        Decimal("0.00"),
    )

    now = datetime.utcnow()
    coupons = db.query(Coupon).filter(
        Coupon.is_active.is_(True),
        Coupon.valid_from <= now,
        Coupon.valid_to >= now,
        (
            Coupon.restaurant_id.is_(None)
            | (Coupon.restaurant_id == cart.restaurant_id)
        ),
    ).all()

    available = []

    for coupon in coupons:
        if item_total < Decimal(str(coupon.min_order_value)):
            continue

        if (
            coupon.total_usage_limit is not None
            and coupon.usage_count >= coupon.total_usage_limit
        ):
            continue

        if coupon.discount_type == "Percentage":
            discount = (
                item_total * Decimal(str(coupon.discount_value)) / Decimal("100")
            )
            if coupon.max_discount is not None:
                discount = min(discount, Decimal(str(coupon.max_discount)))
        else:
            discount = Decimal(str(coupon.discount_value))

        discount = min(discount, item_total)

        available.append({
            "id": coupon.id,
            "code": coupon.code,
            "description": coupon.description,
            "discount_type": coupon.discount_type,
            "discount_value": float(coupon.discount_value),
            "discount_amount": float(discount),
            "min_order_value": float(coupon.min_order_value),
            "restaurant_id": coupon.restaurant_id,
            "valid_to": coupon.valid_to,
        })

    return available
