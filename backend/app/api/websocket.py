from fastapi import WebSocket, WebSocketDisconnect
from typing import List, Dict
import json
import asyncio
import structlog

logger = structlog.get_logger()


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("WebSocket client connected", total_connections=len(self.active_connections))

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        logger.info("WebSocket client disconnected", total_connections=len(self.active_connections))

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: Dict):
        """Broadcast message to all connected clients"""
        if not self.active_connections:
            return

        message_str = json.dumps(message)
        disconnected = []

        for connection in self.active_connections:
            try:
                await connection.send_text(message_str)
            except Exception:
                disconnected.append(connection)

        for conn in disconnected:
            self.active_connections.remove(conn)

    async def broadcast_agent_update(self, agent_id: int, status: str, data: Dict = None):
        """Broadcast agent status update"""
        await self.broadcast({
            "type": "agent_update",
            "agent_id": agent_id,
            "status": status,
            "data": data or {}
        })

    async def broadcast_trade_update(self, trade_id: int, action: str, data: Dict = None):
        """Broadcast trade update"""
        await self.broadcast({
            "type": "trade_update",
            "trade_id": trade_id,
            "action": action,
            "data": data or {}
        })

    async def broadcast_regime_change(self, old_regime: str, new_regime: str, data: Dict = None):
        """Broadcast regime change"""
        await self.broadcast({
            "type": "regime_change",
            "old_regime": old_regime,
            "new_regime": new_regime,
            "data": data or {}
        })

    async def broadcast_alert(self, level: str, message: str, data: Dict = None):
        """Broadcast alert to all clients"""
        await self.broadcast({
            "type": "alert",
            "level": level,
            "message": message,
            "data": data or {}
        })


manager = ConnectionManager()


async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Handle incoming messages from clients
            try:
                message = json.loads(data)
                if message.get("type") == "ping":
                    await manager.send_personal_message(json.dumps({"type": "pong"}), websocket)
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        manager.disconnect(websocket)
