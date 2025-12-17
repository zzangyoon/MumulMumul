from datetime import datetime, timezone
import sys
sys.path.append("../..")

import json
from typing import Dict, List, Literal

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel

from app.services.meeting_chatbot.chatbot_service import MeetingChatbotService
from app.core.mongodb import TeamChatMessage, get_mongo_db

router = APIRouter()
chatbot_service = MeetingChatbotService()

mongo_db = get_mongo_db()
collection = mongo_db["team_chat_messages"]

# 메모리 세션 저장 (임시)
CHAT_SESSIONS: Dict[str, List[Dict]] = {}


# ===========================
# Pydantic Schemas (REST용)
# ===========================
class MeetingChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    createdAt: str  # ISO8601 문자열


class ChatHistoryResponse(BaseModel):
    groupId: str
    userId: int
    messages: List[MeetingChatMessage]


# ===========================
# WebSocket: 회의 미팅 도우미 채팅
# ===========================
@router.websocket("/")
async def meeting_chatbot_ws(websocket: WebSocket):
    """
    회의 미팅 도우미용 WebSocket
    - event: "start_chat" / "query" / "end_chat"
    - 메시지는 team_chat_messages 컬렉션에 type="ai" 으로 저장
    """

    print(f"[MeetingChat] client connected : {websocket.client}")
    await websocket.accept()
    await websocket.send_text(f"Welcome client : {websocket.client}")

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({
                    "event": "error", 
                    "message": "Invalid JSON payload"
                })
                continue

            event = data.get("event")

            # -------------------------
            # 1) start_chat
            # -------------------------
            if event == "start_chat":
                groupId = str(data.get("groupId"))
                user_id = data.get("userId")
                user_name = data.get("userName", "")

                if not groupId:
                    await websocket.send_json({
                        "event": "error",
                        "message": "groupId is required"
                    })
                    continue

                CHAT_SESSIONS[groupId] = []
                print(f"[MeetingChat] 세션 시작 : groupId-{groupId} userId-{user_id}")

                await websocket.send_json({
                    "event": "chat_started",
                    "groupId": groupId,
                    "userId": user_id,
                    "userName": user_name,
                    "message": "회의 미팅 도우미 세션이 시작되었습니다.",
                })

            # -------------------------
            # 2) query (user → AI)
            # -------------------------
            elif event == "query":
                groupId = str(data.get("groupId"))
                user_id = data.get("userId")
                user_name = data.get("userName", "")
                query_text = data.get("query")

                if not groupId:
                    await websocket.send_json({
                        "event": "error",
                        "message": "groupId is required"
                    })
                    continue

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
                        query = query_text,
                        meeting_id = data.get("meeting_id"),
                        group_id = groupId
                    )

                    assistant_doc = {
                        "role": "assistant",
                        "content": result["answer"],
                        "confidence": result["confidence"],
                        "sources": result["sources"],
                        "relevant_segments": result["relevant_segments"],
                        "createdAt": datetime.now(timezone.utc),
                    }

                    collection.insert_one({
                        "roomId": groupId,
                        "type": "ai",
                        "role": "assistant",
                        "userId": 0,
                        "userName": "AI",
                        "message": result["answer"],
                        "createdAt": datetime.now(timezone.utc),
                    })

                    CHAT_SESSIONS[groupId].append(assistant_doc)

                    await websocket.send_json({
                        "event": "answer",
                        "groupId": groupId,
                        "answer" : result["answer"]
                    })

                except Exception as e:
                    await websocket.send_json({
                        "event": "error",
                        "message": f"AI 답변 생성 실패: {e}"
                    })


                # 3) assistant 메시지 저장
                # assistant_doc = {
                #     "roomId": groupId,
                #     "type": "ai",
                #     "role": "assistant",
                #     "userId": None,
                #     "userName": "AI",
                #     "message": assistant_reply,
                #     "createdAt": datetime.utcnow().isoformat(),
                # }
                # collection.insert_one(assistant_doc)
                # CHAT_SESSIONS[groupId].append(assistant_doc)

                # # 클라이언트에게 응답
                # await websocket.send_json({
                #     "event": "answer",
                #     "groupId": groupId,
                #     "answer": assistant_reply,
                # })

            # -------------------------
            # 3) end_chat
            # -------------------------
            elif event == "end_chat":
                groupId = str(data.get("groupId"))
                print(f"[MeetingChat] 세션 종료 : groupId-{groupId}")

                await websocket.send_json({
                    "event": "chat_ended",
                    "groupId": groupId,
                    "message": "회의 미팅 도우미 세션이 종료되었습니다.",
                })
                await websocket.close()
                break

            else:
                await websocket.send_json({
                    "event": "error",
                    "message": f"Unknown event: {event}"
                })

    except WebSocketDisconnect:
        print("[MeetingChat] client disconnected")
        pass
