from collections import defaultdict
import asyncio
import logging

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketManager:
    def __init__(self):
        self.order_connections = defaultdict(list)
        self.restaurant_connections = defaultdict(list)
        self.partner_connections = defaultdict(list)
        self.lock = asyncio.Lock()
        self.loop = None

    async def connect_order(self, order_id: int, websocket: WebSocket):
        self.loop = asyncio.get_running_loop()
        await websocket.accept()
        async with self.lock:
            self.order_connections[order_id].append(websocket)

    async def connect_restaurant(self, user_id: int, websocket: WebSocket):
        self.loop = asyncio.get_running_loop()
        await websocket.accept()
        async with self.lock:
            self.restaurant_connections[user_id].append(websocket)

    async def connect_partner(self, user_id: int, websocket: WebSocket):
        self.loop = asyncio.get_running_loop()
        await websocket.accept()
        async with self.lock:
            self.partner_connections[user_id].append(websocket)

    async def disconnect(self, connections: dict, key: int, websocket: WebSocket):
        async with self.lock:
            clients = connections.get(key, [])
            if websocket in clients:
                clients.remove(websocket)
            if not clients:
                connections.pop(key, None)

    async def _broadcast(self, connections: dict, key: int, message: dict):
        async with self.lock:
            clients = list(connections.get(key, []))

        disconnected = []
        for client in clients:
            try:
                await client.send_json(message)
            except Exception:
                disconnected.append(client)

        for client in disconnected:
            await self.disconnect(connections, key, client)

    async def broadcast_order(self, order_id: int, message: dict):
        await self._broadcast(self.order_connections, order_id, message)

    async def broadcast_restaurant(self, owner_id: int, message: dict):
        await self._broadcast(self.restaurant_connections, owner_id, message)

    async def broadcast_partner(self, partner_user_id: int, message: dict):
        await self._broadcast(self.partner_connections, partner_user_id, message)

    def publish_from_sync(self, coroutine):
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(coroutine, self.loop)
        else:
            coroutine.close()


manager = WebSocketManager()