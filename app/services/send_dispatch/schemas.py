from __future__ import annotations
from enum import Enum
from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime

class QueryPurpose(str, Enum):
    TARGETING = "targeting"          # 대상자 뽑기
    PERSONALIZATION = "personalization"  # 메시지 내용 강화

class DBTable(str, Enum):
    CAMP = "camp"
    USER = "user"
    ATTENDANCE_DAILY = "attendance_daily"
    SESSION_ACTIVITY_LOG = "session_activity_log"

class FilterOp(str, Enum):
    EQ="eq"; IN="in"; LT="lt"; LTE="lte"; GT="gt"; GTE="gte"; BETWEEN="between"; LIKE="like"

from typing import List, Optional, Literal, Any
from pydantic import BaseModel, Field

class DBFilter(BaseModel):
    field: str
    op: Literal["eq", "in", "lt", "lte", "gt", "gte", "between"]
    value: Any

class DBQueryPlan(BaseModel):
    id: Optional[str] = None
    table: str = Field(..., description="DB 테이블명 (camp, user, attendance_daily, ...)")
    fields: List[str] = Field(default_factory=list)
    filters: List[DBFilter] = Field(default_factory=list)
    limit: int = 200
    save_as: Optional[str] = None

class ParsedMessagingRequest(BaseModel):
    message_type: Literal["notice", "dm"]
    target_scope: Literal["camp_all", "user_list"]
    camp_name: Optional[str] = None
    user_names: Optional[List[str]] = None
    topic: str

    query_plans: List[DBQueryPlan] = Field(default_factory=list)

    delivery_channel: Literal["websocket", "stub"] = "websocket"
    urgency: Literal["normal", "high"] = "normal"
    language: Literal["ko", "en"] = "ko"


class SelectTargetsResult(BaseModel):
    camp_id: Optional[int] = Field(default=None, description="캠프 전체 발송이면 필수")
    target_user_ids: List[int] = Field(default_factory=list, description="최종 발송 대상 user_id 목록")

class ComposeNoticeResult(BaseModel):
    title: str = Field(..., description="공지 제목(짧게)")
    message_text: str = Field(..., description="최종 공지 본문(운영진이 그대로 발송 가능)")
    tone: Literal["normal", "urgent"] = Field("normal", description="공지 톤")

class ComposeDM(BaseModel):
    user_id: int = Field(..., description="대상 user_id")
    user_name: Optional[str] = Field(default=None, description="대상 user 이름")
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

    query_results: Dict[str, Any] = Field(default_factory=dict)
    parsed: Optional[ParsedMessagingRequest] = None

    camp_id: Optional[int] = None
    target_user_ids: List[int] = Field(default_factory=list)

    context_data: dict = {}  # 조회 결과를 여기 담기 (attendance 등)

    # 메시지 산출물
    notice_message: Optional[ComposeNoticeResult] = None # notice용(1개)
    dm_messages: Optional[List[ComposeDM]] = None  # dm용

    dispatch_result: Optional[DispatchResult] = None
    dispatch_log_id: Optional[str] = None

    error: Optional[str] = None
    debug: Dict[str, str] = Field(default_factory=dict)
