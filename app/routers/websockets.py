import math
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.user import User
from app.models.order import Order
from app.models.restaurant import Restaurant
from app.models.delivery_partner import DeliveryPartner
from app.routers.auth import SECRET_KEY, ALGORITHM
from app.services.websocket_manager import manager

router = APIRouter(tags=["Real-Time WebSockets"])


def get_user_from_token(db: Session, token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username:
            return None
        user = db.query(User).filter(User.username == username).first()
        if not user or not user.is_active:
            return None
        return user
    except (JWTError, TypeError, ValueError):
        return None


def distance_km(lat1, lon1, lat2, lon2):
    """Calculate approximate distance between two GPS coordinates."""
    if None in (lat1, lon1, lat2, lon2):
        return None

    radius = 6371.0
    lat1, lon1, lat2, lon2 = map(
        math.radians, (float(lat1), float(lon1), float(lat2), float(lon2))
    )
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return round(radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)), 2)


def tracking_payload(db: Session, order: Order):
    restaurant = db.query(Restaurant).filter(
        Restaurant.id == order.restaurant_id
    ).first()

    partner = None
    if order.delivery_partner_id:
        partner = db.query(DeliveryPartner).filter(
            DeliveryPartner.user_id == order.delivery_partner_id
        ).first()

    partner_user = db.query(User).filter(
        User.id == order.delivery_partner_id
    ).first() if order.delivery_partner_id else None

    lat = float(partner.current_latitude) if partner and partner.current_latitude is not None else None
    lon = float(partner.current_longitude) if partner and partner.current_longitude is not None else None

    remaining = None
    eta_minutes = None

    if (
        lat is not None
        and lon is not None
        and restaurant
        and restaurant.latitude is not None
        and restaurant.longitude is not None
    ):
        remaining = distance_km(
            lat, lon, restaurant.latitude, restaurant.longitude
        )

    # Fallback to the order's stored delivery distance when live coordinates
    # are not yet available. This is an estimate, not a road-route calculation.
    if remaining is None and order.distance_km is not None:
        remaining = float(order.distance_km)

    if remaining is not None:
        eta_minutes = round((remaining / 25) * 60)

    return {
        "event": "tracking_update",
        "order_id": order.id,
        "order_number": order.order_number,
        "status": order.status,
        "restaurant_name": restaurant.name if restaurant else None,
        "delivery_partner": partner_user.username if partner_user else None,
        "vehicle_type": partner.vehicle_type if partner else None,
        "vehicle_number": partner.vehicle_number if partner else None,
        "latitude": lat,
        "longitude": lon,
        "last_location_at": (
            partner.last_location_at.isoformat()
            if partner and partner.last_location_at else None
        ),
        "distance_remaining_km": remaining,
        "eta_minutes": eta_minutes,
        "updated_at": datetime.utcnow().isoformat(),
    }


@router.websocket("/ws/orders/{order_id}")
async def order_tracking(websocket: WebSocket, order_id: int, token: str):
    db = SessionLocal()
    connected = False

    try:
        user = get_user_from_token(db, token)
        if not user:
            await websocket.close(code=1008, reason="Invalid authentication token")
            return

        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            await websocket.close(code=1008, reason="Order not found")
            return

        restaurant = db.query(Restaurant).filter(
            Restaurant.id == order.restaurant_id
        ).first()

        allowed = (
            user.role == "ADMIN"
            or order.customer_id == user.id
            or (restaurant and restaurant.owner_id == user.id)
            or order.delivery_partner_id == user.id
        )

        if not allowed:
            await websocket.close(code=1008, reason="Access denied")
            return

        await manager.connect_order(order_id, websocket)
        connected = True

        await websocket.send_json(tracking_payload(db, order))

        # Keep the connection alive. Status/location updates are broadcast
        # to this connection by the manager.
        while True:
            await websocket.receive_text()

    except WebSocketDisconnect:
        pass
    except Exception:
        # Avoid leaving stale connections after unexpected disconnects.
        pass
    finally:
        if connected:
            await manager.disconnect(
                manager.order_connections, order_id, websocket
            )
        db.close()


@router.websocket("/ws/restaurant")
async def restaurant_alerts(websocket: WebSocket, token: str):
    db = SessionLocal()
    connected = False
    user_id = None

    try:
        user = get_user_from_token(db, token)
        if not user or user.role not in ("RESTAURANT_OWNER", "ADMIN"):
            await websocket.close(code=1008, reason="Invalid authentication or role")
            return

        user_id = user.id
        await manager.connect_restaurant(user_id, websocket)
        connected = True
        await websocket.send_json({"event": "connected", "message": "Restaurant alerts connected"})

        while True:
            await websocket.receive_text()

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        if connected:
            await manager.disconnect(
                manager.restaurant_connections, user_id, websocket
            )
        db.close()


@router.websocket("/ws/partner")
async def partner_updates(websocket: WebSocket, token: str):
    db = SessionLocal()
    connected = False
    user_id = None

    try:
        user = get_user_from_token(db, token)
        if not user or user.role != "DELIVERY_PARTNER":
            await websocket.close(code=1008, reason="Invalid authentication or role")
            return

        profile = db.query(DeliveryPartner).filter(
            DeliveryPartner.user_id == user.id
        ).first()

        if not profile:
            await websocket.close(code=1008, reason="Delivery partner profile not found")
            return

        user_id = user.id
        await manager.connect_partner(user_id, websocket)
        connected = True
        await websocket.send_json({
            "event": "connected",
            "message": "Delivery partner updates connected",
        })

        # Partners can send {"latitude": 13.08, "longitude": 80.27}
        # periodically to update their current location.
        while True:
            data = await websocket.receive_json()

            if not isinstance(data, dict):
                await websocket.send_json({"event": "error", "message": "Send a JSON object"})
                continue

            if "latitude" not in data or "longitude" not in data:
                # Other messages can be ignored; the connection can still
                # receive delivery-offer notifications.
                continue

            try:
                lat = float(data["latitude"])
                lon = float(data["longitude"])
                if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    raise ValueError
            except (TypeError, ValueError):
                await websocket.send_json({
                    "event": "error",
                    "message": "Invalid latitude or longitude",
                })
                continue

            profile.current_latitude = lat
            profile.current_longitude = lon
            profile.last_location_at = datetime.utcnow()
            db.commit()

            active_orders = db.query(Order).filter(
                Order.delivery_partner_id == user.id,
                Order.status.in_(["PICKED_UP", "OUT_FOR_DELIVERY"]),
            ).all()

            for order in active_orders:
                await manager.broadcast_order(
                    order.id, tracking_payload(db, order)
                )

            await websocket.send_json({
                "event": "location_saved",
                "latitude": lat,
                "longitude": lon,
                "updated_at": profile.last_location_at.isoformat(),
            })

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        if connected:
            await manager.disconnect(
                manager.partner_connections, user_id, websocket
            )
        db.close()