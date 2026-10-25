
import re

from app.utils.location import calculate_distance_km
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, ConfigDict, field_validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.restaurant import Restaurant as RestaurantModel
from app.models.menu_item import MenuItem
from app.models.coupon import Coupon

router = APIRouter(prefix="/restaurants", tags=["Restaurants"])


class RestaurantCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    address: str = Field(min_length=1, max_length=500)
    phone: str = Field(min_length=10, max_length=10)
    owner_id: int = Field(default=1, gt=0)
    description: str | None = None
    cuisine_type: str = Field(default="Other", min_length=1, max_length=100)
    is_open: bool = True
    is_approved: bool = False
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    is_active: bool = True
    delivery_radius_km: float = Field(default=5.0, gt=0)
    avg_preparation_minutes: int = Field(default=20, ge=0)

    @field_validator("name", "address", "phone", "cuisine_type")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field cannot be empty")
        return value

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        if not re.fullmatch(r"\d{10}", value):
            raise ValueError("Phone number must contain exactly 10 digits")
        return value


class RestaurantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    address: str
    phone: str
    cuisine_type: str
    is_open: bool
    is_approved: bool


@router.get("/health")
def restaurants_health():
    return {"message": "Restaurants router is working"}


@router.post("/", response_model=RestaurantResponse, status_code=201)
def create_restaurant(
    data: RestaurantCreate,
    db: Session = Depends(get_db),
):
    restaurant = RestaurantModel(**data.model_dump())
    db.add(restaurant)

    try:
        db.commit()
        db.refresh(restaurant)
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Could not create restaurant; check for duplicate or invalid data",
        )

    return restaurant


# Keep /nearby above /{restaurant_id}.
@router.get("/nearby")
def get_nearby_restaurants(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    name: str | None = Query(default=None),
    cuisine_type: str | None = Query(default=None),
    veg_only: bool = Query(default=False),
    min_rating: float = Query(default=0, ge=0, le=5),
    has_offers: bool = Query(default=False),
    sort_by: str = Query(
        default="distance",
        pattern="^(distance|rating|estimated_delivery_minutes)$",
    ),
    order: str = Query(default="asc", pattern="^(asc|desc)$"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = db.query(RestaurantModel).filter(
        RestaurantModel.is_open.is_(True),
        RestaurantModel.is_approved.is_(True),
        RestaurantModel.is_active.is_(True),
        RestaurantModel.latitude.isnot(None),
        RestaurantModel.longitude.isnot(None),
    )

    if name and name.strip():
        query = query.filter(
            RestaurantModel.name.ilike(f"%{name.strip()}%")
        )

    if cuisine_type and cuisine_type.strip():
        query = query.filter(
            RestaurantModel.cuisine_type.ilike(
                f"%{cuisine_type.strip()}%"
            )
        )

    if min_rating > 0:
        query = query.filter(
            func.coalesce(RestaurantModel.average_rating, 0) >= min_rating
        )

    if has_offers:
        active_coupon_exists = (
            db.query(Coupon.id)
            .filter(
                Coupon.restaurant_id == RestaurantModel.id,
                Coupon.is_active.is_(True),
                Coupon.valid_from <= func.now(),
                Coupon.valid_to >= func.now(),
            )
            .exists()
        )
        query = query.filter(active_coupon_exists)

    restaurants = query.all()
    results = []

    for restaurant in restaurants:
        distance = calculate_distance_km(
            latitude,
            longitude,
            restaurant.latitude,
            restaurant.longitude,
        )

        if distance > restaurant.delivery_radius_km:
            continue

        if veg_only:
            veg_item = (
                db.query(MenuItem.id)
                .filter(
                    MenuItem.restaurant_id == restaurant.id,
                    MenuItem.is_available.is_(True),
                    func.lower(MenuItem.category).like("%veg%"),
                )
                .first()
            )
            if not veg_item:
                continue

        travel_minutes = round((distance / 20.0) * 60)
        estimated_delivery = (
            restaurant.avg_preparation_minutes + travel_minutes
        )

        results.append({
            "id": restaurant.id,
            "name": restaurant.name,
            "description": restaurant.description,
            "address": restaurant.address,
            "phone": restaurant.phone,
            "cuisine_type": restaurant.cuisine_type,
            "latitude": restaurant.latitude,
            "longitude": restaurant.longitude,
            "distance_km": round(distance, 2),
            "average_rating": getattr(restaurant, "average_rating", 0) or 0,
            "estimated_delivery_minutes": estimated_delivery,
            "delivery_radius_km": restaurant.delivery_radius_km,
        })

    sort_keys = {
        "distance": "distance_km",
        "rating": "average_rating",
        "estimated_delivery_minutes": "estimated_delivery_minutes",
    }

    key = sort_keys[sort_by]
    results.sort(
        key=lambda item: item[key],
        reverse=(order == "desc"),
    )

    return results[skip:skip + limit]


@router.get("/", response_model=list[RestaurantResponse])
def get_restaurants(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return (
        db.query(RestaurantModel)
        .order_by(RestaurantModel.id)
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.get("/{restaurant_id}", response_model=RestaurantResponse)
def get_restaurant(
    restaurant_id: int,
    db: Session = Depends(get_db),
):
    restaurant = db.query(RestaurantModel).filter(
        RestaurantModel.id == restaurant_id
    ).first()

    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")

    return restaurant


@router.put("/{restaurant_id}", response_model=RestaurantResponse)
def update_restaurant(
    restaurant_id: int,
    data: RestaurantCreate,
    db: Session = Depends(get_db),
):
    restaurant = db.query(RestaurantModel).filter(
        RestaurantModel.id == restaurant_id
    ).first()

    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")

    for key, value in data.model_dump().items():
        setattr(restaurant, key, value)

    try:
        db.commit()
        db.refresh(restaurant)
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Could not update restaurant; check for duplicate or invalid data",
        )

    return restaurant


@router.delete("/{restaurant_id}")
def delete_restaurant(
    restaurant_id: int,
    db: Session = Depends(get_db),
):
    restaurant = db.query(RestaurantModel).filter(
        RestaurantModel.id == restaurant_id
    ).first()

    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")

    db.delete(restaurant)
    db.commit()
    return {"message": "Restaurant deleted successfully"}
