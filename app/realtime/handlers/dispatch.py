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
        "message_id": int,
        "kind": "dm" | "notice",
        "receivedAt": "ISO8601"
      }
    """
    message_id = payload.get("messageId")
    user_id = state.user_id
    print(f"[Dispatch][ACK] 메세지 확인 요청 user_id={user_id} payload={payload}")

    db_gen = get_db()
    db = next(db_gen)

    mr = (
        db.query(MessageRecipient)
        .filter(MessageRecipient.recipient_id == user_id)
        .filter(MessageRecipient.message_id == message_id)
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

    print(f"[Dispatch][ACK] 메세지 확인 완료 user_id={user_id} payload={payload}")

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
