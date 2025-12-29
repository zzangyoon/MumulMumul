from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import WebSocket

from app.realtime.ws_manager import ClientState  # UnifiedWebSocketManager의 ClientState
from app.services.learning_chatbot.service import answer

from app.core.mongodb import ChatMessage
from app.services.db_service.learning_chatbot import (
    CHAT_SESSIONS,
    save_learning_chatbot_log,
)


async def start_chat(websocket: WebSocket, state: ClientState, payload: Dict[str, Any]) -> Dict[str, Any]:
    session_id = payload.get("sessionId")
    user_id = payload.get("userId")

    if not session_id:
        return {"domain": "system", "event": "error", "payload": {"message": "sessionId is required"}}

    # 새 세션 초기화
    CHAT_SESSIONS[session_id] = []
    print(f"[LearningChat] 세션 시작 : sessionId-{session_id} userId-{user_id}")

    return {
        "domain": "learning",
        "event": "chat_started",
        "payload": {
            "sessionId": session_id,
            "userId": user_id,
            "message": "새로운 학습 세션이 시작되었습니다.",
        },
    }


async def query(websocket: WebSocket, state: ClientState, payload: Dict[str, Any]) -> Dict[str, Any]:
    session_id = payload.get("sessionId")
    user_id = payload.get("userId")
    query_text = payload.get("query")
    grade = payload.get("grade")

    if not session_id:
        return {"domain": "system", "event": "error", "payload": {"message": "sessionId is required"}}
    if not query_text:
        return {"domain": "system", "event": "error", "payload": {"message": "query is required"}}

    if session_id not in CHAT_SESSIONS:
        CHAT_SESSIONS[session_id] = []
        print(f"[LearningChat] 세션 자동 생성 : sessionId-{session_id} userId-{user_id}")

    # user 메시지 저장
    user_record = ChatMessage(
        role="user",
        content=query_text,
        created_at=datetime.now(),
    )
    save_learning_chatbot_log(user_id, session_id, [user_record])
    CHAT_SESSIONS[session_id].append(user_record)

    print(f"[LearningChat] 쿼리 요청 : sessionId-{session_id} userId-{user_id} query-{query_text}")

    # AI 답변 생성
    assistant_reply = answer(query_text, grade, history=CHAT_SESSIONS[session_id])

    assistant_record = ChatMessage(
        role="assistant",
        content=assistant_reply,
        created_at=datetime.now(),
    )
    save_learning_chatbot_log(user_id, session_id, [assistant_record])
    CHAT_SESSIONS[session_id].append(assistant_record)

    return {
        "domain": "learning",
        "event": "answer",
        "payload": {
            "sessionId": session_id,
            "answer": assistant_reply,
        },
    }


async def end_chat(websocket: WebSocket, state: ClientState, payload: Dict[str, Any]) -> Dict[str, Any]:
    session_id = payload.get("sessionId")
    user_id = payload.get("userId")
    print(f"[LearningChat] 세션 종료 : sessionId-{session_id} userId-{user_id}")

    # 여기서 websocket.close() 하지 말 것!
    # (통합 라우터가 응답을 보내야 해서)
    return {
        "domain": "learning",
        "event": "chat_ended",
        "payload": {
            "sessionId": session_id,
            "message": "학습 세션이 종료되었습니다.",
        },
    }
