from fastapi import WebSocket


class VideoRoomWebSocketManager:
    def __init__(self):
        self.rooms: dict[str, set[WebSocket]] = {}

    async def connect(self, token: str, websocket: WebSocket):
        await websocket.accept()
        self.rooms.setdefault(token, set()).add(websocket)

    def disconnect(self, token: str, websocket: WebSocket):
        sockets = self.rooms.get(token)
        if not sockets:
            return
        sockets.discard(websocket)
        if not sockets:
            self.rooms.pop(token, None)

    async def broadcast(self, token: str, message: dict, exclude: WebSocket | None = None):
        sockets = list(self.rooms.get(token, set()))
        for socket in sockets:
            if socket is exclude:
                continue
            try:
                await socket.send_json(message)
            except Exception:
                self.disconnect(token, socket)


video_room_ws_manager = VideoRoomWebSocketManager()
