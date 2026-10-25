
from pydantic import BaseModel, Field


class DeliveryOTPRequest(BaseModel):
    otp: str = Field(
        min_length=4,
        max_length=4,
        pattern=r"^\d{4}$",
        description="Four-digit delivery OTP",
    )
