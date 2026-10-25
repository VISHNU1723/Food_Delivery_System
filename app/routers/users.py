
from fastapi import APIRouter

router = APIRouter(
    prefix="/users",
    tags=["Users"]
)


@router.get("/health")
def users_health():
    return {
        "message": "Users router is working"
    }
