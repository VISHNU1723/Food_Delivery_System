
from fastapi import APIRouter

router = APIRouter(
    prefix="/payments",
    tags=["Payments"]
)


@router.get("/health")
def payments_health():
    return {
        "message": "Payments router is working"
    }
