from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import WebSocket

from app.realtime.ws_manager import ClientState
from app.services.meeting_chatbot.chatbot_service import MeetingChatbotService
from app.core.mongodb import get_mongo_db

chatbot_service = MeetingChatbotService()

mongo_db = get_mongo_db()
collection = mongo_db["team_chat_messages"]

# 메모리 세션 저장(임시)
CHAT_SESSIONS: Dict[str, list] = {}


async def start_chat(websocket: WebSocket, state: ClientState, payload: Dict[str, Any]) -> Dict[str, Any]:
    groupId = str(payload.get("groupId"))
    user_id = payload.get("userId")
    user_name = payload.get("userName", "")

    if not groupId or groupId == "None":
        return {"domain": "system", "event": "error", "payload": {"message": "groupId is required"}}

    CHAT_SESSIONS[groupId] = []
    print(f"[MeetingChat] 세션 시작 : groupId-{groupId} userId-{user_id}")

    return {
        "domain": "meeting",
        "event": "chat_started",
        "payload": {
            "groupId": groupId,
            "userId": user_id,
            "userName": user_name,
            "message": "회의 미팅 도우미 세션이 시작되었습니다.",
        },
    }


async def query(websocket: WebSocket, state: ClientState, payload: Dict[str, Any]) -> Dict[str, Any]:
    groupId = str(payload.get("groupId"))
    user_id = payload.get("userId")
    user_name = payload.get("userName", "")
    query_text = payload.get("query")

    if not groupId or groupId == "None":
        return {"domain": "system", "event": "error", "payload": {"message": "groupId is required"}}
    if not query_text:
        return {"domain": "system", "event": "error", "payload": {"message": "query is required"}}

    if groupId not in CHAT_SESSIONS:
        CHAT_SESSIONS[groupId] = []
        print(f"[MeetingChat] 세션 자동 생성 : groupId-{groupId}")

    # 1) user 메시지 저장
    user_doc = {
        "roomId": groupId,
        "type": "ai",
        "role": "user",
        "userId": user_id,
        "userName": user_name,
        "message": query_text,
        "createdAt": datetime.now(timezone.utc),
    }
    collection.insert_one(user_doc)
    CHAT_SESSIONS[groupId].append(user_doc)

    print(f"[MeetingChat] user query : {query_text}")

    # 2) AI 답변 생성
    try:
        result = await chatbot_service.ask(
            query=query_text,
            meeting_id=payload.get("meeting_id"),
            group_id=groupId,
        )
    except Exception as e:
        return {"domain": "system", "event": "error", "payload": {"message": f"AI 답변 생성 실패: {e}"}}

    # 3) assistant 메시지 저장 (Mongo)
    collection.insert_one({
        "roomId": groupId,
        "type": "ai",
        "role": "assistant",
        "userId": 0,
        "userName": "AI",
        "message": result["answer"],
        "createdAt": datetime.now(timezone.utc),
    })

    return {
        "domain": "meeting",
        "event": "answer",
        "payload": {
            "groupId": groupId,
            "answer": result["answer"],
        },
    }


async def end_chat(websocket: WebSocket, state: ClientState, payload: Dict[str, Any]) -> Dict[str, Any]:
    groupId = str(payload.get("groupId"))
    print(f"[MeetingChat] 세션 종료 : groupId-{groupId}")

    return {
        "domain": "meeting",
        "event": "chat_ended",
        "payload": {
            "groupId": groupId,
            "message": "회의 미팅 도우미 세션이 종료되었습니다.",
        },
    }
