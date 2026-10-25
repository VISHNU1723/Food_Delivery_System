
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Literal
import re


class AddressCreate(BaseModel):
    label: Literal["Home", "Work", "Other"]
    address_line: str = Field(min_length=5, max_length=500)
    city: str = Field(min_length=2, max_length=100)
    pincode: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    is_default: bool = False

    @field_validator("pincode")
    @classmethod
    def validate_pincode(cls, value: str) -> str:
        if not re.fullmatch(r"\d{6}", value):
            raise ValueError("Pincode must contain exactly 6 digits")
        return value


class AddressUpdate(BaseModel):
    label: Literal["Home", "Work", "Other"] | None = None
    address_line: str | None = Field(default=None, min_length=5, max_length=500)
    city: str | None = Field(default=None, min_length=2, max_length=100)
    pincode: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    is_default: bool | None = None

    @field_validator("pincode")
    @classmethod
    def validate_pincode(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(r"\d{6}", value):
            raise ValueError("Pincode must contain exactly 6 digits")
        return value


class AddressResponse(AddressCreate):
    id: int
    customer_id: int

    model_config = ConfigDict(from_attributes=True)
