
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.user import User
from app.models.delivery_partner import DeliveryPartner

USERNAME = "test_delivery_partner"
EMAIL = "deliverypartner@test.com"
VEHICLE_NUMBER = "TEST-BIKE-001"

db: Session = SessionLocal()

try:
    user = db.query(User).filter(User.username == USERNAME).first()

    if not user:
        print("User not found. Register this user through /auth/register first.")
    else:
        user.role = "DELIVERY_PARTNER"
        user.is_active = True
        user.is_approved = True

        partner = (
            db.query(DeliveryPartner)
            .filter(DeliveryPartner.user_id == user.id)
            .first()
        )

        if not partner:
            partner = DeliveryPartner(
                user_id=user.id,
                vehicle_type="Bike",
                vehicle_number=VEHICLE_NUMBER,
                is_approved=True,
                is_online=False,
            )
            db.add(partner)
        else:
            partner.is_approved = True

        db.commit()
        print("Delivery partner setup successful.")
        print("Username:", user.username)
        print("User ID:", user.id)
        print("Partner profile ID:", partner.id)

except Exception:
    db.rollback()
    raise
finally:
    db.close()
