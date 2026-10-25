
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.models.menu_item import MenuItem
from app.schemas.menu import (
    MenuItemCreate,
    MenuItemUpdate,
    MenuItemResponse,
)

router = APIRouter(prefix="/menu", tags=["Menu"])


@router.get("/health")
def menu_health():
    return {"message": "Menu router is working"}


@router.post("/", response_model=MenuItemResponse, status_code=201)
def create_menu_item(
    data: MenuItemCreate,
    db: Session = Depends(get_db),
):
    item = MenuItem(**data.model_dump())
    db.add(item)

    try:
        db.commit()
        db.refresh(item)
        return item
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Menu item could not be created due to a data conflict",
        )


@router.get("/", response_model=list[MenuItemResponse])
def get_menu_items(db: Session = Depends(get_db)):
    return db.query(MenuItem).all()


@router.get("/{item_id}", response_model=MenuItemResponse)
def get_menu_item(item_id: int, db: Session = Depends(get_db)):
    item = db.query(MenuItem).filter(MenuItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Menu item not found")
    return item


@router.put("/{item_id}", response_model=MenuItemResponse)
def update_menu_item(
    item_id: int,
    data: MenuItemUpdate,
    db: Session = Depends(get_db),
):
    item = db.query(MenuItem).filter(MenuItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Menu item not found")

    updates = data.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(item, key, value)

    try:
        db.commit()
        db.refresh(item)
        return item
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Menu item could not be updated due to a data conflict",
        )


@router.delete("/{item_id}", status_code=200)
def delete_menu_item(item_id: int, db: Session = Depends(get_db)):
    item = db.query(MenuItem).filter(MenuItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Menu item not found")

    db.delete(item)
    db.commit()
    return {"message": "Menu item deleted successfully"}
