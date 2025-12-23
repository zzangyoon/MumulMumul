import json
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from app.core.ws_manager import ws_manager, ConnKey

router = APIRouter()


# ---------------------------
# Event handlers
# ---------------------------
async def handle_ping(key: ConnKey, payload: Dict[str, Any]) -> Dict[str, Any]:
    return {"type": "pong", "payload": {"server_time": datetime.utcnow().isoformat()}}

async def handle_ack(key: ConnKey, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    클라가 DM/공지 수신 확인을 보낼 때.
    payload 예:
      { "message_id": "...", "received_at": "...", "type": "dm" }
    """
    print(f"[WS][ACK] user_id={key.user_id} session_id={key.session_id} payload={payload}")
    # TODO: DB에 ack 저장하고 싶으면 여기서 저장
    return None  # 응답 굳이 안 줘도 됨


ws_manager.register_handler("ping", handle_ping)
ws_manager.register_handler("ack", handle_ack)


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    user_id: int = Query(...),
    session_id: str = Query(...),
):
    """
    접속: ws://host/ws?user_id=123&session_id=abc
    """
    await ws_manager.connect(websocket, user_id=user_id, session_id=session_id)
    key = ConnKey(user_id=user_id, session_id=session_id)

    # 접속 직후 hello (옵션)
    await websocket.send_text(json.dumps({
        "type": "hello",
        "payload": {"user_id": user_id, "session_id": session_id}
    }, ensure_ascii=False))

    try:
        while True:
            raw = await websocket.receive_text()
            print(f"[WS] recv user_id={user_id} session_id={session_id} raw={raw}")

            resp = await ws_manager.handle_incoming(key, raw)
            if resp is not None:
                await websocket.send_text(json.dumps(resp, ensure_ascii=False))

    except WebSocketDisconnect:
        ws_manager.disconnect(user_id=user_id, session_id=session_id)
    except Exception as e:
        print(f"[WS] fatal error user_id={user_id} session_id={session_id} err={e}")
        ws_manager.disconnect(user_id=user_id, session_id=session_id)
