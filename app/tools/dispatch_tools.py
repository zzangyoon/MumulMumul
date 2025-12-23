# app/tools/dispatch_tools.py
from typing import Any, List, Dict
from langchain_core.tools import tool

from app.core import ws_manager

@tool
def dispatch_stub(user_id: int, message_text: str) -> Dict:
    """
    stub 전송: 실제로 보내지는 않지만 성공한 것처럼 처리
    """
    print(f"[STUB DISPATCH] user_id={user_id}")
    return {
        "user_id": user_id, 
        "status": "sent",
        "channel": "stub",
    }

@tool
async def dispatch_websocket_dm(user_id: int, message_text: str, message_id: str | None = None) -> Dict[str, Any]:
    """
    WebSocket으로 개인 DM을 전송한다.
    - user_id에 연결된 모든 session으로 브로드캐스트한다.
    - message_id는 클라 ACK 매칭용(선택)
    """
    payload = {
        "type": "dm",
        "payload": {
            "message_id": message_id,
            "text": message_text,
        }
    }
    print(f"[WS DISPATCH] dm user_id={user_id} message_id={message_id}")
    return await ws_manager.send_to_user(user_id, payload)