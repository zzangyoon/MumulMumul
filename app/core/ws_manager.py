import json
from dataclasses import dataclass
from typing import Any, Dict, Optional, Callable, Awaitable, Set, Tuple

from fastapi import WebSocket


@dataclass(frozen=True)
class ConnKey:
    user_id: int
    session_id: str


ServerEventHandler = Callable[[ConnKey, Dict[str, Any]], Awaitable[Optional[Dict[str, Any]]]]


class WebSocketManager:
    """
    - user_id + session_id 단위로 연결 관리
    - user_id로 send 하면 해당 user의 모든 세션에 브로드캐스트 가능
    - 이벤트 타입 기반 핸들러 라우팅 지원
    """

    def __init__(self):
        self._conns: Dict[ConnKey, WebSocket] = {}
        self._handlers: Dict[str, ServerEventHandler] = {}

    # ---------------------------
    # Connection lifecycle
    # ---------------------------
    async def connect(self, websocket: WebSocket, user_id: int, session_id: str):
        await websocket.accept()
        key = ConnKey(user_id=user_id, session_id=session_id)
        self._conns[key] = websocket
        print(f"[WS] connected user_id={user_id} session_id={session_id} total={len(self._conns)}")

    def disconnect(self, user_id: int, session_id: str):
        key = ConnKey(user_id=user_id, session_id=session_id)
        self._conns.pop(key, None)
        print(f"[WS] disconnected user_id={user_id} session_id={session_id} total={len(self._conns)}")

    def has_connection(self, user_id: int) -> bool:
        return any(k.user_id == user_id for k in self._conns.keys())

    def get_sessions(self, user_id: int) -> Set[str]:
        return {k.session_id for k in self._conns.keys() if k.user_id == user_id}

    # ---------------------------
    # Event handler registry
    # ---------------------------
    def register_handler(self, event_type: str, handler: ServerEventHandler):
        self._handlers[event_type] = handler

    # ---------------------------
    # Send helpers
    # ---------------------------
    async def send_to_session(self, user_id: int, session_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        key = ConnKey(user_id=user_id, session_id=session_id)
        ws = self._conns.get(key)
        if not ws:
            return {"user_id": user_id, "session_id": session_id, "sent": 0, "failed": 1, "status": "no_connection"}

        try:
            await ws.send_text(json.dumps(payload, ensure_ascii=False))
            return {"user_id": user_id, "session_id": session_id, "sent": 1, "failed": 0, "status": "ok"}
        except Exception as e:
            print(f"[WS] send_to_session failed user_id={user_id} session_id={session_id} err={e}")
            self._conns.pop(key, None)
            return {"user_id": user_id, "session_id": session_id, "sent": 0, "failed": 1, "status": "send_failed"}

    async def send_to_user(self, user_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
        targets = [k for k in self._conns.keys() if k.user_id == user_id]
        if not targets:
            return {"user_id": user_id, "sent": 0, "failed": 0, "status": "no_connection"}

        sent, failed = 0, 0
        dead: list[ConnKey] = []
        text = json.dumps(payload, ensure_ascii=False)

        for k in targets:
            ws = self._conns.get(k)
            if not ws:
                continue
            try:
                await ws.send_text(text)
                sent += 1
            except Exception as e:
                print(f"[WS] send_to_user failed user_id={user_id} session_id={k.session_id} err={e}")
                failed += 1
                dead.append(k)

        for k in dead:
            self._conns.pop(k, None)

        return {"user_id": user_id, "sent": sent, "failed": failed, "status": "ok" if sent else "failed"}

    async def broadcast(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        sent, failed = 0, 0
        dead: list[ConnKey] = []
        text = json.dumps(payload, ensure_ascii=False)

        for k, ws in self._conns.items():
            try:
                await ws.send_text(text)
                sent += 1
            except Exception as e:
                print(f"[WS] broadcast failed user_id={k.user_id} session_id={k.session_id} err={e}")
                failed += 1
                dead.append(k)

        for k in dead:
            self._conns.pop(k, None)

        return {"sent": sent, "failed": failed, "status": "ok" if sent else "failed"}

    # ---------------------------
    # Incoming message loop
    # ---------------------------
    async def handle_incoming(self, key: ConnKey, raw_text: str) -> Optional[Dict[str, Any]]:
        """
        클라 -> 서버 메시지 포맷(권장):
        {
          "type": "ping" | "ack" | "presence" | ...,
          "payload": {...},
          "request_id": "optional"
        }
        """
        try:
            msg = json.loads(raw_text)
        except Exception:
            return {"type": "error", "payload": {"reason": "invalid_json"}}

        event_type = msg.get("type")
        payload = msg.get("payload", {})

        if not event_type:
            return {"type": "error", "payload": {"reason": "missing_type"}}

        handler = self._handlers.get(event_type)
        if not handler:
            return {"type": "error", "payload": {"reason": f"unsupported_type:{event_type}"}}

        return await handler(key, payload)

ws_manager = WebSocketManager()
