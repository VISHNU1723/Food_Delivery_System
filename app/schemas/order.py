
from datetime import datetime
from typing import Literal
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CartItemCreate(BaseModel):
    menu_item_id: int = Field(gt=0)
    quantity: int = Field(gt=0, le=10)


class CartItemResponse(BaseModel):
    id: int
    menu_item_id: int
    quantity: int
    unit_price: float
    item_name: str

    model_config = ConfigDict(from_attributes=True)


class CartResponse(BaseModel):
    items: list[CartItemResponse]
    total_amount: float


class OrderCreate(BaseModel):
    restaurant_id: int = Field(gt=0)
    address_id: int | None = Field(default=None, gt=0)
    delivery_address: str = Field(min_length=5, max_length=500)
    items: list[CartItemCreate] = Field(min_length=1)
    payment_method: Literal["COD", "ONLINE"] = "COD"
    tip_amount: float = Field(default=0, ge=0)

    @field_validator("delivery_address")
    @classmethod
    def validate_delivery_address(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Delivery address cannot be empty")
        return value.strip()


class OrderResponse(BaseModel):
    id: int
    order_number: str | None = None
    customer_id: int
    restaurant_id: int
    address_id: int | None = None
    delivery_partner_id: int | None = None

    status: Literal[
        "PLACED",
        "ACCEPTED",
        "CONFIRMED",
        "PREPARING",
        "READY",
        "READY_FOR_PICKUP",
        "PICKED_UP",
        "OUT_FOR_DELIVERY",
        "DELIVERED",
        "REJECTED",
        "CANCELLED",
    ]

    item_total: float = 0
    coupon_code: str | None = None
    discount_amount: float = 0
    packaging_charges: float = 0
    delivery_fee: float = 0
    platform_fee: float = 0
    gst_amount: float = 0
    tip_amount: float = 0
    grand_total: float = 0
    total_amount: float

    delivery_address: str
    payment_method: Literal["COD", "ONLINE"]
    payment_status: Literal["PENDING", "PAID", "FAILED", "REFUNDED"]

    distance_km: float = 0
    placed_at: datetime
    delivered_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
