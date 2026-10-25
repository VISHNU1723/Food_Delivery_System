
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.order import Order
from app.models.rating import Rating
from app.models.restaurant import Restaurant
from app.models.user import User
from app.routers.auth import get_current_user
from app.schemas.rating import RatingCreate, RatingResponse

router = APIRouter(tags=["Ratings"])


@router.post(
    "/orders/{order_id}/rating",
    response_model=RatingResponse,
    status_code=201,
)
def rate_order(
    order_id: int,
    payload: RatingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    order = db.query(Order).filter(Order.id == order_id).first()

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.customer_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Only the customer who placed this order can rate it",
        )

    if order.status != "DELIVERED":
        raise HTTPException(
            status_code=400,
            detail="Only delivered orders can be rated",
        )

    existing = db.query(Rating).filter(
        Rating.order_id == order_id
    ).first()

    if existing:
        raise HTTPException(
            status_code=409,
            detail="This order has already been rated",
        )

    restaurant = db.query(Restaurant).filter(
        Restaurant.id == order.restaurant_id
    ).first()

    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")

    rating = Rating(
        order_id=order.id,
        customer_id=current_user.id,
        restaurant_rating=payload.restaurant_rating,
        partner_rating=payload.partner_rating,
        comment=payload.comment,
    )

    db.add(rating)
    db.flush()

    ratings = (
        db.query(Rating)
        .join(Order, Rating.order_id == Order.id)
        .filter(Order.restaurant_id == restaurant.id)
        .all()
    )

    restaurant.average_rating = round(
        sum(item.restaurant_rating for item in ratings) / len(ratings),
        2,
    )

    db.commit()
    db.refresh(rating)

    return rating


@router.get(
    "/restaurants/{restaurant_id}/ratings",
    response_model=list[RatingResponse],
)
def get_restaurant_ratings(
    restaurant_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    restaurant = db.query(Restaurant).filter(
        Restaurant.id == restaurant_id
    ).first()

    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")

    return (
        db.query(Rating)
        .join(Order, Rating.order_id == Order.id)
        .filter(Order.restaurant_id == restaurant_id)
        .order_by(Rating.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
