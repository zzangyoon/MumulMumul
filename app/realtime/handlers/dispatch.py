from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import WebSocket

from app.core.db import get_db
from app.core.schemas import MessageRecipient
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

    db_gen = get_db()
    db = next(db_gen)

    mr = (
        db.query(MessageRecipient)
        .filter(MessageRecipient.recipient_id == payload.userId)
        .filter(MessageRecipient.message_id == payload.messageId)
        .first()
    )
    if mr is None:
        print(f"[Dispatch][ACK] 존재 하지 않는 메세지 user_id={user_id} payload={payload}")
        return None

    # 이미 확인했으면 idempotent
    if not mr.is_confirmed:
        mr.is_confirmed = True
        mr.confirmed_at = datetime.now(timezone.utc)
        db.commit()
    else:
        print(f"[Dispatch][ACK] 이미 확인한 메세지 user_id={user_id} payload={payload}")

    print(f"[Dispatch][ACK] user_id={user_id} payload={payload}")

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
