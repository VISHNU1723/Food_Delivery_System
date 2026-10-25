from pydantic import BaseModel, Field, ConfigDict


class RatingCreate(BaseModel):
    restaurant_rating: int = Field(ge=1, le=5)
    partner_rating: int = Field(ge=1, le=5)
    comment: str | None = None


class RatingResponse(BaseModel):
    id: int
    order_id: int
    customer_id: int
    restaurant_rating: int
    partner_rating: int
    comment: str | None
    created_at: object

    model_config = ConfigDict(from_attributes=True)