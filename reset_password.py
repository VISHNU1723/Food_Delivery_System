
from app.database import SessionLocal
from app.models.user import User
from app.routers.auth import pwd_context

db = SessionLocal()

try:
    user = db.query(User).filter(
        User.username == "vishnu_test02"
    ).first()

    if user is None:
        print("User not found")
    else:
        new_password = "FoodAdmin@123"
        user.hashed_password = pwd_context.hash(new_password)
        db.commit()

        print("Password reset successfully")
        print("Username: vishnu_test02")
        print("New password: FoodAdmin@123")

finally:
    db.close()
