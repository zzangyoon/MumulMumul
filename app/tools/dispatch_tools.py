# app/tools/dispatch_tools.py
from typing import List, Dict
from langchain_core.tools import tool

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
