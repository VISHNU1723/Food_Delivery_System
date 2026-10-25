
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.address import Address
from app.models.user import User
from app.schemas.address import (
    AddressCreate,
    AddressUpdate,
    AddressResponse,
)
from app.routers.auth import SECRET_KEY, ALGORITHM

router = APIRouter(prefix="/addresses", tags=["Addresses"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_customer(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
        )
        username = payload.get("sub")

        if not username:
            raise credentials_error

    except JWTError:
        raise credentials_error

    customer = db.query(User).filter(
        User.username == username
    ).first()

    if customer is None:
        raise credentials_error

    return customer


def make_default(
    db: Session,
    customer_id: int,
    selected_address_id: int | None = None,
) -> None:
    db.query(Address).filter(
        Address.customer_id == customer_id
    ).update(
        {Address.is_default: False},
        synchronize_session="fetch",
    )

    if selected_address_id is not None:
        db.query(Address).filter(
            Address.id == selected_address_id,
            Address.customer_id == customer_id,
        ).update(
            {Address.is_default: True},
            synchronize_session="fetch",
        )


@router.post(
    "",
    response_model=AddressResponse,
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/",
    response_model=AddressResponse,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
def create_address(
    data: AddressCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_customer),
):
    customer_id = current_user.id

    has_addresses = db.query(Address.id).filter(
        Address.customer_id == customer_id
    ).first() is not None

    address_data = data.model_dump()

    if address_data["is_default"] or not has_addresses:
        make_default(db, customer_id)
        address_data["is_default"] = True

    address = Address(
        customer_id=customer_id,
        **address_data,
    )

    try:
        db.add(address)
        db.commit()
        db.refresh(address)
        return address
    except Exception:
        db.rollback()
        raise


@router.get(
    "",
    response_model=list[AddressResponse],
)
@router.get(
    "/",
    response_model=list[AddressResponse],
    include_in_schema=False,
)
def get_addresses(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_customer),
):
    return db.query(Address).filter(
        Address.customer_id == current_user.id
    ).order_by(Address.id.asc()).all()


@router.put(
    "/{address_id}",
    response_model=AddressResponse,
)
def update_address(
    address_id: int,
    data: AddressUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_customer),
):
    customer_id = current_user.id

    address = db.query(Address).filter(
        Address.id == address_id,
        Address.customer_id == customer_id,
    ).first()

    if address is None:
        raise HTTPException(
            status_code=404,
            detail="Address not found",
        )

    updates = data.model_dump(exclude_unset=True)

    if updates.get("is_default") is True:
        make_default(db, customer_id)

    for field, value in updates.items():
        setattr(address, field, value)

    try:
        db.commit()
        db.refresh(address)
        return address
    except Exception:
        db.rollback()
        raise


@router.delete("/{address_id}")
def delete_address(
    address_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_customer),
):
    customer_id = current_user.id

    address = db.query(Address).filter(
        Address.id == address_id,
        Address.customer_id == customer_id,
    ).first()

    if address is None:
        raise HTTPException(
            status_code=404,
            detail="Address not found",
        )

    was_default = address.is_default

    try:
        db.delete(address)
        db.flush()

        if was_default:
            replacement = db.query(Address).filter(
                Address.customer_id == customer_id
            ).order_by(Address.id.asc()).first()

            if replacement:
                replacement.is_default = True

        db.commit()
        return {"message": "Address deleted successfully"}

    except Exception:
        db.rollback()
        raise


@router.put(
    "/{address_id}/default",
    response_model=AddressResponse,
)
def set_default_address(
    address_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_customer),
):
    customer_id = current_user.id

    address = db.query(Address).filter(
        Address.id == address_id,
        Address.customer_id == customer_id,
    ).first()

    if address is None:
        raise HTTPException(
            status_code=404,
            detail="Address not found",
        )

    try:
        make_default(db, customer_id, address_id)
        db.commit()
        db.refresh(address)
        return address
    except Exception:
        db.rollback()
        raise
