
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.menu_item import MenuItem
from app.models.order import Order
from app.models.order_item import OrderItem
from app.schemas.order import CartItemCreate

router = APIRouter(
    prefix="/order-items",
    tags=["Order Items"],
)


@router.get("/health")
def order_items_health():
    return {"message": "Order Items router is working"}


@router.get("/{order_id}")
def get_order_items(order_id: int, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()

    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    items = (
        db.query(OrderItem)
        .filter(OrderItem.order_id == order_id)
        .all()
    )

    return items


@router.post("/{order_id}", status_code=201)
def add_order_item(
    order_id: int,
    data: CartItemCreate,
    db: Session = Depends(get_db),
):
    order = db.query(Order).filter(Order.id == order_id).first()

    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.status != "PLACED":
        raise HTTPException(
            status_code=400,
            detail="Items can only be added to an order with PLACED status",
        )

    menu_item = (
        db.query(MenuItem)
        .filter(
            MenuItem.id == data.menu_item_id,
            MenuItem.restaurant_id == order.restaurant_id,
        )
        .first()
    )

    if menu_item is None:
        raise HTTPException(
            status_code=404,
            detail="Menu item not found for this restaurant",
        )

    if not menu_item.is_available:
        raise HTTPException(
            status_code=400,
            detail="Menu item is not available",
        )

    item = OrderItem(
        order_id=order_id,
        menu_item_id=menu_item.id,
        quantity=data.quantity,
        unit_price=menu_item.price,
        item_name=menu_item.name,
    )

    try:
        db.add(item)
        db.flush()

        items = (
            db.query(OrderItem)
            .filter(OrderItem.order_id == order_id)
            .all()
        )

        order.total_amount = sum(
            float(existing.unit_price) * existing.quantity
            for existing in items
        )

        db.commit()
        db.refresh(item)
        return item
    except Exception:
        db.rollback()
        raise
