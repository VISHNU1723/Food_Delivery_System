from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.cart import Cart
from app.models.cart_item import CartItem
from app.models.coupon import Coupon
from app.models.menu_item import MenuItem
from app.models.order import Order
from app.models.user import User
from app.routers.addresses import get_current_customer

router = APIRouter(prefix="/cart", tags=["Cart"])


def get_or_create_cart(db: Session, customer_id: int) -> Cart:
    cart = db.query(Cart).filter(
        Cart.customer_id == customer_id
    ).first()

    if cart is None:
        cart = Cart(customer_id=customer_id)
        db.add(cart)
        db.commit()
        db.refresh(cart)

    return cart


def calculate_discount(coupon: Coupon, item_total: Decimal) -> Decimal:
    if coupon.discount_type == "Percentage":
        discount = (
            item_total * Decimal(str(coupon.discount_value))
            / Decimal("100")
        )

        if coupon.max_discount is not None:
            discount = min(
                discount,
                Decimal(str(coupon.max_discount))
            )
    else:
        discount = Decimal(str(coupon.discount_value))

    return min(discount, item_total).quantize(Decimal("0.01"))


def build_cart_response(db: Session, cart: Cart) -> dict:
    items = db.query(CartItem).filter(
        CartItem.cart_id == cart.id
    ).all()

    item_total = sum(
        (
            Decimal(str(item.unit_price)) * item.quantity
            for item in items
        ),
        Decimal("0.00"),
    )

    applied_coupon = None
    discount = Decimal("0.00")

    if cart.coupon_id is not None:
        coupon = db.query(Coupon).filter(
            Coupon.id == cart.coupon_id
        ).first()

        now = datetime.utcnow()

        if (
            coupon is not None
            and coupon.is_active
            and coupon.valid_from <= now <= coupon.valid_to
            and item_total >= Decimal(str(coupon.min_order_value))
            and (
                coupon.restaurant_id is None
                or coupon.restaurant_id == cart.restaurant_id
            )
            and items
        ):
            discount = calculate_discount(coupon, item_total)
            applied_coupon = coupon.code
        else:
            cart.coupon_id = None
            db.commit()

    return {
        "cart_id": cart.id,
        "restaurant_id": cart.restaurant_id,
        "items": [
            {
                "id": item.id,
                "menu_item_id": item.menu_item_id,
                "item_name": item.item_name,
                "unit_price": float(item.unit_price),
                "quantity": item.quantity,
                "line_total": float(
                    Decimal(str(item.unit_price)) * item.quantity
                ),
            }
            for item in items
        ],
        "item_total": float(item_total),
        "applied_coupon": applied_coupon,
        "discount": float(discount),
        "total_after_discount": float(item_total - discount),
    }


@router.get("")
def get_cart(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_customer),
):
    cart = get_or_create_cart(db, current_user.id)
    return build_cart_response(db, cart)


@router.post("/items", status_code=201)
def add_cart_item(
    data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_customer),
):
    menu_item_id = data.get("menu_item_id")
    quantity = data.get("quantity")

    if (
        not isinstance(menu_item_id, int)
        or isinstance(menu_item_id, bool)
        or menu_item_id <= 0
    ):
        raise HTTPException(
            status_code=422,
            detail="menu_item_id must be a positive integer",
        )

    if (
        not isinstance(quantity, int)
        or isinstance(quantity, bool)
        or not 1 <= quantity <= 10
    ):
        raise HTTPException(
            status_code=422,
            detail="Quantity must be between 1 and 10",
        )

    menu_item = db.query(MenuItem).filter(
        MenuItem.id == menu_item_id
    ).first()

    if menu_item is None:
        raise HTTPException(status_code=404, detail="Menu item not found")

    if not menu_item.is_available:
        raise HTTPException(
            status_code=400,
            detail="Menu item is unavailable",
        )

    cart = get_or_create_cart(db, current_user.id)

    if (
        cart.restaurant_id is not None
        and cart.restaurant_id != menu_item.restaurant_id
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "Your cart has items from another restaurant. "
                "Clear the cart to continue"
            ),
        )

    existing = db.query(CartItem).filter(
        CartItem.cart_id == cart.id,
        CartItem.menu_item_id == menu_item.id,
    ).first()

    new_quantity = quantity + (
        existing.quantity if existing else 0
    )

    if new_quantity > 10:
        raise HTTPException(
            status_code=422,
            detail="Quantity cannot exceed 10 per item",
        )

    try:
        cart.restaurant_id = menu_item.restaurant_id

        if existing:
            existing.quantity = new_quantity
            existing.unit_price = menu_item.price
            existing.item_name = menu_item.name
        else:
            db.add(
                CartItem(
                    cart_id=cart.id,
                    menu_item_id=menu_item.id,
                    quantity=quantity,
                    unit_price=menu_item.price,
                    item_name=menu_item.name,
                )
            )

        db.commit()
        db.refresh(cart)
        return build_cart_response(db, cart)

    except Exception:
        db.rollback()
        raise


@router.put("/items/{item_id}")
def update_cart_item(
    item_id: int,
    data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_customer),
):
    quantity = data.get("quantity")

    if (
        not isinstance(quantity, int)
        or isinstance(quantity, bool)
        or not 1 <= quantity <= 10
    ):
        raise HTTPException(
            status_code=422,
            detail="Quantity must be between 1 and 10",
        )

    cart = db.query(Cart).filter(
        Cart.customer_id == current_user.id
    ).first()

    if cart is None:
        raise HTTPException(status_code=404, detail="Cart not found")

    item = db.query(CartItem).filter(
        CartItem.id == item_id,
        CartItem.cart_id == cart.id,
    ).first()

    if item is None:
        raise HTTPException(
            status_code=404,
            detail="Cart item not found",
        )

    item.quantity = quantity
    db.commit()
    db.refresh(cart)

    return build_cart_response(db, cart)


@router.delete("/items/{item_id}")
def remove_cart_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_customer),
):
    cart = db.query(Cart).filter(
        Cart.customer_id == current_user.id
    ).first()

    if cart is None:
        raise HTTPException(status_code=404, detail="Cart not found")

    item = db.query(CartItem).filter(
        CartItem.id == item_id,
        CartItem.cart_id == cart.id,
    ).first()

    if item is None:
        raise HTTPException(
            status_code=404,
            detail="Cart item not found",
        )

    db.delete(item)
    db.flush()

    if db.query(CartItem).filter(
        CartItem.cart_id == cart.id
    ).count() == 0:
        cart.restaurant_id = None
        cart.coupon_id = None

    db.commit()
    return build_cart_response(db, cart)


@router.delete("")
def clear_cart(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_customer),
):
    cart = db.query(Cart).filter(
        Cart.customer_id == current_user.id
    ).first()

    if cart is None:
        return {"message": "Cart is already empty"}

    db.query(CartItem).filter(
        CartItem.cart_id == cart.id
    ).delete(synchronize_session=False)

    cart.restaurant_id = None
    cart.coupon_id = None
    db.commit()

    return {
        "message": "Cart cleared successfully",
        "cart_id": cart.id,
        "items": [],
        "item_total": 0.0,
        "applied_coupon": None,
        "discount": 0.0,
        "total_after_discount": 0.0,
    }


@router.post("/apply-coupon")
def apply_coupon(
    data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_customer),
):
    code = data.get("code")

    if not isinstance(code, str) or not code.strip():
        raise HTTPException(
            status_code=422,
            detail="Coupon code is required",
        )

    cart = db.query(Cart).filter(
        Cart.customer_id == current_user.id
    ).first()

    if cart is None:
        raise HTTPException(status_code=400, detail="Your cart is empty")

    items = db.query(CartItem).filter(
        CartItem.cart_id == cart.id
    ).all()

    if not items:
        raise HTTPException(status_code=400, detail="Your cart is empty")

    coupon = db.query(Coupon).filter(
        Coupon.code == code.strip().upper()
    ).first()

    if coupon is None:
        raise HTTPException(status_code=400, detail="Invalid coupon code")

    now = datetime.utcnow()

    if not coupon.is_active:
        raise HTTPException(status_code=400, detail="Coupon is inactive")

    if now < coupon.valid_from or now > coupon.valid_to:
        raise HTTPException(
            status_code=400,
            detail="Coupon is not valid at this time",
        )

    if (
        coupon.restaurant_id is not None
        and coupon.restaurant_id != cart.restaurant_id
    ):
        raise HTTPException(
            status_code=400,
            detail="Coupon is not valid for this restaurant",
        )

    item_total = sum(
        (
            Decimal(str(item.unit_price)) * item.quantity
            for item in items
        ),
        Decimal("0.00"),
    )

    if item_total < Decimal(str(coupon.min_order_value)):
        raise HTTPException(
            status_code=400,
            detail="Cart total is below the coupon minimum order value",
        )

    if (
        coupon.total_usage_limit is not None
        and coupon.usage_count >= coupon.total_usage_limit
    ):
        raise HTTPException(
            status_code=400,
            detail="Coupon usage limit has been reached",
        )

    # Per-user limits and first-order eligibility will be enforced
    # with order-usage tracking when checkout is integrated.

    cart.coupon_id = coupon.id
    db.commit()
    db.refresh(cart)

    return {
        "message": "Coupon applied successfully",
        **build_cart_response(db, cart),
    }


@router.delete("/coupon")
def remove_coupon(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_customer),
):
    cart = db.query(Cart).filter(
        Cart.customer_id == current_user.id
    ).first()

    if cart is None or cart.coupon_id is None:
        raise HTTPException(
            status_code=404,
            detail="No coupon is applied to your cart",
        )

    cart.coupon_id = None
    db.commit()
    db.refresh(cart)

    return {
        "message": "Coupon removed successfully",
        **build_cart_response(db, cart),
    }