from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import WebSocket

from app.realtime.ws_manager import ClientState


async def ack(websocket: WebSocket, state: ClientState, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    클라가 DM/공지 수신 확인을 보낼 때.
    payload 예:
      {
        "message_id": "uuid",
        "kind": "dm" | "notice",
        "receivedAt": "ISO8601"
      }
    """
    user_id = state.user_id
    print(f"[Dispatch][ACK] user_id={user_id} payload={payload}")

    # TODO: 필요하면 DB 저장
    # save_dispatch_ack(user_id, payload)

    return {
        "domain": "dispatch",
        "event": "ack_ok",
        "payload": {
            "ok": True,
            "serverAt": datetime.now(timezone.utc).isoformat(),
        },
    }


async def ping(websocket: WebSocket, state: ClientState, payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "domain": "dispatch",
        "event": "pong",
        "payload": {"serverAt": datetime.now(timezone.utc).isoformat()},
    }
