# app/core/mongodb.py

from datetime import date, datetime, timezone
from typing import Literal, Optional, List, Tuple, Type, Dict, Any

from bson import ObjectId
from pydantic import BaseModel, Field
from pymongo import MongoClient
from app.config import MONGO_URL, MONGO_DB_NAME
from app.services.curriculum.schemas import CurriculumAIInsights, CurriculumCharts, CurriculumSummaryCards, CurriculumTables


# =====================================
# 1. MongoDB 연결
# =====================================
mongo_client = MongoClient(MONGO_URL, tz_aware=True, tzinfo=timezone.utc)
mongo_db = mongo_client[MONGO_DB_NAME]

def get_mongo_db() -> MongoClient:
    """
    MongoDB 데이터베이스 인스턴스 반환
    """
    return mongo_db


# =====================================
# 2. MongoDB 모델 레지스트리 및 초기화
# =====================================
class MongoModelSpec(BaseModel):
    model: Type[BaseModel]
    collection_name: str
    indexes: List[Tuple[str, int]]  # [("field", 1), ("created_at", -1)] 이런식


MONGO_MODELS: List[MongoModelSpec] = []


def register_mongo_model(
    model: Type[BaseModel],
    collection_name: str,
    indexes: List[Tuple[str, int]],
):
    """
    새로운 Mongo 문서 모델을 등록하는 함수.
    - 모델 클래스(BaseModel)
    - 사용할 컬렉션 이름
    - 만들고 싶은 인덱스 리스트
    """
    spec = MongoModelSpec(
        model=model,
        collection_name=collection_name,
        indexes=indexes,
    )
    MONGO_MODELS.append(spec)


def init_mongo(db):
    """
    서버 시작 시 한 번만 호출해서
    - 각 컬렉션에 대해 필요한 인덱스를 생성함.
    """
    for spec in MONGO_MODELS:
        coll = db[spec.collection_name]
        for field, order in spec.indexes:
            coll.create_index([(field, order)])

    print(f"[MongoDB] Initialized {len(MONGO_MODELS)} collections/indexes.")


# =====================================
# 3. 도메인 모델 정의
# =====================================
# =====================================
# 3-1. Learning Chat Log 모델 정의
# =====================================
# 학습 챗봇과의 채팅 로그 모델
class CurriculumInsights(BaseModel):
    """
    curriculum_insights: 질문 분석 정보
    질문이 어떤 토픽(topic)을 다루는지,
    커리큘럼 내/외 범위(scope),
    질문 패턴(pattern_tags),
    질문 의도(intent)을 담음.
    """
    id: str = Field(..., description="로그 문서의 고유 ID")
    topic: Optional[str] = Field(None, description="커리큘럼 토픽 키 (예: pandas, visualization, career 등)")
    scope: Optional[Literal["in", "out"]] = Field(None, description="'in'=커리큘럼 내 / 'out'=커리큘럼 외")
    pattern_tags: List[str] = Field(default_factory=list, description="질문 패턴 태그 리스트")
    intent: Optional[str] = Field(None, description="질문 의도 한 줄 요약")

class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime = datetime.utcnow()

class LearningChatLog(BaseModel):
    """
    학습 챗봇 채팅 로그 저장 모델 (MongoDB)

    - user_id: SQL(User.user_id)와 연결
    - session_id: 세션 식별자 (옵션)
    - camp_id: SQL(Camp.camp_id)와 연결 (옵션)
    - role: 'user' or 'assistant'
    - content: 실제 채팅 내용
    - curriculum_scope: 커리큘럼 내/외 ("in" / "out")
    - question_category: numpy / pandas / portfolio 등 분류 태그
    - created_at: 생성 시각
    """
    user_id: int
    session_id: Optional[int] = None
    camp_id: Optional[int] = None

    role: Literal["user", "assistant"]
    content: str

    curriculum_insights: Optional[CurriculumInsights] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)


register_mongo_model(
    LearningChatLog,
    collection_name="learning_chat_logs",
    indexes=[
        ("session_id", 1),
        ("user_id", 1),
        ("created_at", -1),
    ],
)



# =====================================
# 3-2. Team Chat Message 모델 정의
# =====================================
class TeamChatMessage(BaseModel):
    """
    팀 채팅방 메시지 로그

    - room_id: 채팅방 ID (SQL ChatRoom.id 와 연결)
    - user_id: SQL(User.user_id)와 연결
    - user_name: 메시지 보낸 유저 이름 (조회 편의용, 캐시 개념)
    - message: 실제 채팅 내용
    - created_at: 메시지 생성 시각
    - type: "team" (팀 채팅) or "ai" (AI 챗봇)
    - role: "user" (사용자 메시지) or "assistant" (AI
    """
    room_id: str
    user_id: int
    user_name: str
    message: str
    created_at: datetime = datetime.utcnow()
    type: Literal["team", "ai"] = "team"
    role: Optional[Literal["user", "assistant"]] = None


# TeamChatMessage 모델을 Mongo 레지스트리에 등록
register_mongo_model(
    TeamChatMessage,
    collection_name="team_chat_messages",
    indexes=[
        ("room_id", 1),
        ("user_id", 1),
        ("created_at", -1),
    ]
)


# =====================================
# 3-3. Curriculum Config 모델 정의
# =====================================
class CurriculumWeek(BaseModel):
    """
    한 주차에 대한 커리큘럼 정보.
    - week_index: 1, 2, 3 ...
    - week_label: "1주차", "Week 1" 등 표시용
    - topics: 해당 주차에 다루는 토픽 키 리스트 (예: ["python_basics", "pandas"])
    """
    week_index: int = Field(..., ge=1)
    week_label: str = Field(..., description="표시용 라벨 (예: '1주차')")
    topics: List[str] = Field(default_factory=list, description="토픽 키 리스트")


class CurriculumConfig(BaseModel):
    """
    캠프별 커리큘럼 구조 설정 (MongoDB에 1캠프당 1문서 저장)

    - camp_id: SQL Camp.camp_id 와 연결
    - weeks: 주차별 토픽 구조
    """
    camp_id: int = Field(..., description="캠프 ID (SQL Camp.camp_id)")
    weeks: List[CurriculumWeek] = Field(
        default_factory=list,
        description="주차별 커리큘럼 구조",
    )

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# Mongo 레지스트리에 등록
register_mongo_model(
    CurriculumConfig,
    collection_name="curriculum_configs",
    indexes=[
        ("camp_id", 1),
    ],
)

# =====================================
# 3-4. Curriculum Report 모델 정의
# =====================================

class CurriculumReport(BaseModel):
    """
    커리큘럼 리포트 서비스의 최종 출력 구조.
    Streamlit 화면은 이 Payload 하나를 받아서 그대로 렌더링하면 됨.
    """

    camp_id: int = Field(..., description="캠프 ID")
    camp_name: str = Field(..., description="캠프 이름 (예: '백엔드 캠프 1기')")
    week_index: int = Field(..., description="N주차 숫자 (1부터 시작)")
    week_label: str = Field(..., description="예: '1주차', '3주차'")
    week_start: date = Field(..., description="리포트 기준 주차 시작일")
    week_end: date = Field(..., description="리포트 기준 주차 종료일")
    raw_stats: Optional[Dict[str, Any]] = None

    summary_cards: CurriculumSummaryCards
    charts: CurriculumCharts
    tables: CurriculumTables
    ai_insights: CurriculumAIInsights

# Mongo 레지스트리에 등록
register_mongo_model(
    CurriculumReport,
    collection_name="curriculum_reports",
    indexes=[
        ("camp_id", 1),
        ("week_index", 1),
        ("created_at", -1)
    ],
)

# =====================================
# 3-3. Meeting Transcript 모델 정의
# =====================================
class MeetingSegment(BaseModel):
    """회의 세그먼트"""
    segment_id: str
    user_id: int
    speaker_name: str
    text: str
    start_time_ms: int  # 상대 시간
    end_time_ms: int
    absolute_start_ms: int  # 절대 시간
    absolute_end_ms: int
    confidence: float
    timestamp_display: str  # "[00:05]"


class OverlapInfo(BaseModel):
    """겹침 구간 정보"""
    overlap_type: Literal["voice_voice", "voice_chat"]

    # 공통 필드
    speaker1: str
    speaker2: str
    overlap_start_ms: int

    # voice_voice 전용
    segment1_id: Optional[str] = None
    segment2_id: Optional[str] = None
    overlap_duration_ms: Optional[int] = None
    overlap_end_ms: Optional[int] = None

    # voice_chat 전용
    voice_segment_id: Optional[str] = None
    chat_segment_id: Optional[str] = None
    chat_timestamp_ms: Optional[int] = None
    voice_start_ms: Optional[int] = None
    voice_end_ms: Optional[int] = None


class MeetingTranscript(BaseModel):
    """회의 전체 전사본"""
    meeting_id: str
    title: str
    start_time: str
    end_time: Optional[str] = None
    duration_ms: int
    participant_count: int
    organizer_id: int
    
    # 전체 텍스트 (타임스탬프 + 화자 포함)
    full_text: str
    
    # 세그먼트 리스트 (시간순 정렬됨)
    segments: List[MeetingSegment]
    
    # 겹침 정보
    overlaps: List[OverlapInfo] = []
    
    # 통계
    total_segments: int
    speakers: List[Dict[str, Any]]
    
    # 메타데이터
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# MeetingTranscript 모델 등록
register_mongo_model(
    MeetingTranscript,
    collection_name="meeting_transcripts",
    indexes=[
        ("meeting_id", 1),
        ("organizer_id", 1),
        ("created_at", -1),
    ],
)


# =====================================
# 3-4. Meeting Summary 모델 정의
# =====================================
class MeetingSummary(BaseModel):
    """회의 요약본"""
    meeting_id: str
    summary_text: str
    key_points: List[str] = []
    action_items: List[str] = []
    next_agenda: List[str] = []
    decisions: List[str] = []
    
    # 메타데이터
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    model_used: str = "gpt-4o-mini"


# MeetingSummary 모델 등록
register_mongo_model(
    MeetingSummary,
    collection_name="meeting_summaries",
    indexes=[
        ("meeting_id", 1),
        ("generated_at", -1),
        ],
)

# =====================================
# 3-5. 출결 리포트 모델 정의
# =====================================
class AttendanceSummary(BaseModel):
    attendance_rate: float
    total_students: int
    high_risk_count: int
    warning_count: int
    late_rate: Optional[float] = None

class AttendanceStudentStat(BaseModel):
    student_id: int
    name: str
    attendance_rate: float
    absent_count: int
    late_count: int
    early_leave_count: int
    pattern_type: Optional[str] = None
    risk_level: Literal["고위험", "위험", "주의", "정상"]
    trend: Optional[float] = None
    ops_action: Optional[str] = None

class AttendanceReport(BaseModel):
    camp_id: int
    camp_name: str
    target_date: datetime

    summary: AttendanceSummary
    students: List[AttendanceStudentStat]

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
