from __future__ import annotations
from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class ParsedMessagingRequest(BaseModel):
    message_type: Literal["notice", "dm"] = "notice"
    target_scope: Literal["camp_all", "user_list", "query"] = "camp_all"

    camp_name: Optional[str] = Field(default=None, description="camp_all/query에서 사용")
    user_names: Optional[List[str]] = Field(default=None, description="user_list에서 사용")
    topic: str = Field(..., description="예: 'QR 코드 출결'")

    requested_user_ids: Optional[List[int]] = None
    target_query: Optional[Dict[str, Any]] = None

    delivery_channel: Literal["stub", "websocket"] = "websocket"
    urgency: Literal["normal", "high"] = "normal"
    language: Literal["ko"] = "ko"

class SelectTargetsResult(BaseModel):
    camp_id: Optional[int] = Field(default=None, description="캠프 전체 발송이면 필수")
    target_user_ids: List[int] = Field(default_factory=list, description="최종 발송 대상 user_id 목록")

class ComposeNoticeResult(BaseModel):
    title: str = Field(..., description="공지 제목(짧게)")
    message_text: str = Field(..., description="최종 공지 본문(운영진이 그대로 발송 가능)")
    tone: Literal["normal", "urgent"] = Field("normal", description="공지 톤")

class ComposeDM(BaseModel):
    user_id: int = Field(..., description="대상 user_id")
    message_text: str = Field(..., description="최종 DM 본문(운영진이 그대로 발송 가능)")
    # 5가지 성향에 맞춘 개인화 메시지
    personality_tone: Literal["friendly", "formal", "concise", "detailed", "encouraging"] = Field(
        "friendly", description="개인화 톤"
    )

class ComposeDMResult(BaseModel):
    messages: List[ComposeDM] = Field(..., description="대상별 DM 메시지 리스트")

class DispatchResult(BaseModel):
    channel: Literal["stub", "websocket"] = "stub"
    mode: Literal["broadcast", "per_user"] = "broadcast"

    attempted: int = 0
    sent: int = 0
    skipped: int = 0
    failed: int = 0
    failures: List[Dict[str, str]] = Field(default_factory=list)

class MessagingAgentState(BaseModel):
    sender_id: Optional[int] = None

    request_text: str
    current_time: datetime

    parsed: Optional[ParsedMessagingRequest] = None

    camp_id: Optional[int] = None
    target_user_ids: List[int] = Field(default_factory=list)

    # 메시지 산출물
    notice_message: Optional[ComposeNoticeResult] = None # notice용(1개)
    dm_messages: Optional[List[ComposeDM]] = None  # dm용

    dispatch_result: Optional[DispatchResult] = None
    dispatch_log_id: Optional[str] = None

    error: Optional[str] = None
    debug: Dict[str, str] = Field(default_factory=dict)
