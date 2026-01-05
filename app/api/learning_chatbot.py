# app/api/learning_chatbot_router.py

from datetime import datetime
import sys
sys.path.append("../..")

import json
from typing import Dict, List, Literal, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel
from app.services.learning_chatbot.service import answer

from app.core.mongodb import ChatMessage
from app.services.db_service.learning_chatbot import CHAT_SESSIONS, get_learning_chatbot_log, save_learning_chatbot_log

router = APIRouter()

# ===========================
# Pydantic Schemas (REST용)
# ===========================
class ChatHistoryResponse(BaseModel):
    sessionId: int
    userId: int
    messages: List[ChatMessage]

# ===========================
# REST: 히스토리 조회 API
# ===========================
@router.get("/history/{user_id}/{session_id}",
    response_model=ChatHistoryResponse,
)
def get_chat_history(user_id: int, session_id: int) -> List[ChatMessage]:
    """
    이전 채팅 기록 조회용 GET API
    """
    messages = get_learning_chatbot_log(userId=user_id, sessionId=session_id)
    if messages is None:
        raise HTTPException(status_code=404, detail="Session not found")

    return ChatHistoryResponse(
        sessionId=session_id,
        userId=user_id,
        messages=[
            {
             "role": msg.role, 
             "content": msg.content, 
             "created_at": msg.created_at
             }
            for msg in messages],
    )
