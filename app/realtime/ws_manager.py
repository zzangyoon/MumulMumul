import json
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple

from fastapi import WebSocket


@dataclass
class ClientState:
    """
    연결별 상태 저장 (필요한 것만 최소로)
    """
    user_id: Optional[int] = None
    # dispatch push용: user_id -> ws 매핑 위해 필요
    # learning/meeting은 sessionId/groupId를 payload로 받으니
    # 여긴 최소로만


Handler = Callable[[WebSocket, ClientState, Dict[str, Any]], Awaitable[Optional[Dict[str, Any]]]]


class WebSocketManager:
    """
    단일 WebSocket endpoint에서:
      - domain+event 기반 핸들러 라우팅
      - user_id 등록(register) 기반 push(send_to_user) 지원
    """

    def __init__(self):
        self._handlers: Dict[Tuple[str, str], Handler] = {}
        self._client_state: Dict[WebSocket, ClientState] = {}
        self._user_ws: Dict[int, WebSocket] = {}  # MVP: user_id당 1개 연결만 (필요시 multi-session으로 확장 가능)

    # ---------- handler registry ----------
    def register(self, domain: str, event: str, handler: Handler):
        self._handlers[(domain, event)] = handler

    # ---------- connection lifecycle ----------
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self._client_state[websocket] = ClientState()
        print(f"[WS] connected client={websocket.client}")

    def disconnect(self, websocket: WebSocket):
        st = self._client_state.pop(websocket, None)
        if st and st.user_id and self._user_ws.get(st.user_id) is websocket:
            self._user_ws.pop(st.user_id, None)
            print(f"[WS] unregistered user_id={st.user_id}")
        print(f"[WS] disconnected client={websocket.client}")

    # ---------- message dispatch ----------
    async def handle_message(self, websocket: WebSocket, raw_text: str) -> Optional[Dict[str, Any]]:
        try:
            msg = json.loads(raw_text)
        except Exception:
            return {"domain": "system", "event": "error", "payload": {"message": "Invalid JSON"}}

        domain = msg.get("domain")
        event = msg.get("event")
        payload = msg.get("payload", {})

        if not domain or not event:
            return {"domain": "system", "event": "error", "payload": {"message": "domain/event required"}}

        handler = self._handlers.get((domain, event))
        if not handler:
            return {"domain": "system", "event": "error", "payload": {"message": f"Unknown: {domain}.{event}"}}

        state = self._client_state.get(websocket) or ClientState()
        self._client_state[websocket] = state

        return await handler(websocket, state, payload)

    # ---------- push: server -> user ----------
    async def send_to_user(self, user_id: int, domain: str, event: str, payload: Dict[str, Any]) -> bool:
        ws = self._user_ws.get(user_id)
        if not ws:
            print(f"[WS] send_to_user failed (offline) user_id={user_id}")
            return False
    
        await ws.send_json({"domain": domain, "event": event, "payload": payload})
        print(f"[WS] pushed to user_id={user_id} domain={domain} event={event}")
        return True

    # ---------- built-in handlers ----------
    async def handle_register(self, websocket: WebSocket, state: ClientState, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        클라가 연결 직후 자신의 user_id를 등록해야 dispatch push가 가능해짐.
        payload: { "userId": 123 }
        """
        user_id = payload.get("userId")
        if not user_id:
            return {"domain": "system", "event": "error", "payload": {"message": "userId required"}}

        state.user_id = int(user_id)
        self._user_ws[state.user_id] = websocket
        print(f"[WS] registered user_id={state.user_id}")

        return {"domain": "system", "event": "registered", "payload": {"userId": state.user_id}}


ws_manager = WebSocketManager()
