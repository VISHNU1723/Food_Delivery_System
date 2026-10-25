
from pydantic import BaseModel, ConfigDict, Field


class MenuItemCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    description: str | None = None
    price: float = Field(gt=0)
    restaurant_id: int = Field(gt=0)
    category: str = Field(min_length=2, max_length=100)


class MenuItemUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=150)
    description: str | None = None
    price: float | None = Field(default=None, gt=0)
    restaurant_id: int | None = Field(default=None, gt=0)
    category: str | None = Field(default=None, min_length=2, max_length=100)
    is_available: bool | None = None


class MenuItemResponse(BaseModel):
    id: int
    name: str
    description: str | None = None
    price: float
    restaurant_id: int
    category: str
    is_available: bool = True

    model_config = ConfigDict(from_attributes=True)
