
from datetime import datetime
from typing import Literal
import re

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class CouponCreate(BaseModel):
    code: str = Field(min_length=3, max_length=50)
    description: str | None = None
    discount_type: Literal["Percentage", "Flat"]
    discount_value: float = Field(gt=0)
    max_discount: float | None = Field(default=None, gt=0)
    min_order_value: float = Field(default=0, ge=0)
    restaurant_id: int | None = None
    valid_from: datetime
    valid_to: datetime
    total_usage_limit: int | None = Field(default=None, gt=0)
    per_user_limit: int = Field(default=1, gt=0)
    first_order_only: bool = False

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        value = value.strip().upper()
        if not re.fullmatch(r"[A-Z0-9_-]{3,50}", value):
            raise ValueError(
                "Coupon code must be 3–50 characters using letters, numbers, _ or -"
            )
        return value

    @model_validator(mode="after")
    def validate_coupon(self):
        if self.valid_to <= self.valid_from:
            raise ValueError("valid_to must be after valid_from")

        if self.discount_type == "Percentage":
            if not 1 <= self.discount_value <= 100:
                raise ValueError(
                    "Percentage discount must be between 1 and 100"
                )

        if self.discount_type == "Flat" and self.max_discount is not None:
            raise ValueError(
                "max_discount is only valid for Percentage coupons"
            )

        return self


class CouponUpdate(BaseModel):
    description: str | None = None
    discount_type: Literal["Percentage", "Flat"] | None = None
    discount_value: float | None = Field(default=None, gt=0)
    max_discount: float | None = Field(default=None, gt=0)
    min_order_value: float | None = Field(default=None, ge=0)
    restaurant_id: int | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    total_usage_limit: int | None = Field(default=None, gt=0)
    per_user_limit: int | None = Field(default=None, gt=0)
    first_order_only: bool | None = None

    @field_validator("discount_type")
    @classmethod
    def validate_discount_type(cls, value):
        return value

    @model_validator(mode="after")
    def validate_coupon_update(self):
        if (
            self.valid_from is not None
            and self.valid_to is not None
            and self.valid_to <= self.valid_from
        ):
            raise ValueError("valid_to must be after valid_from")

        if self.discount_type == "Percentage":
            if self.discount_value is not None and not (
                1 <= self.discount_value <= 100
            ):
                raise ValueError(
                    "Percentage discount must be between 1 and 100"
                )

        if self.discount_type == "Flat" and self.max_discount is not None:
            raise ValueError(
                "max_discount is only valid for Percentage coupons"
            )

        return self


class CouponResponse(BaseModel):
    id: int
    code: str
    description: str | None
    discount_type: str
    discount_value: float
    max_discount: float | None
    min_order_value: float
    restaurant_id: int | None
    valid_from: datetime
    valid_to: datetime
    total_usage_limit: int | None
    usage_count: int
    per_user_limit: int
    first_order_only: bool
    created_by: int
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
