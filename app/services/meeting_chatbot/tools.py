from typing import Optional, List, Dict, Any
from langchain_core.tools import tool
from pydantic import Field
from app.core.logger import setup_logger
from app.core.db import SessionLocal
from app.core.schemas import Meeting
from app.core.mongodb import get_mongo_db
from app.services.meeting.mongodb_service import MongoMeetingService
from app.services.meeting.vectorStore_service import VectorStoreService

logger = setup_logger(__name__)

# ===================================================================
# 헬퍼 함수
# ===================================================================
def _clean_field_value(value: Any, default: str="") -> str:
    """FieldInfo 객체 또는 None을 안전하게 문자열로 반환"""
    if value is None:
        return default
    
    if hasattr(value, "__class__") and "FieldInfo" in str(type(value)):
        logger.debug(f"FieldInfo 객체 감지 및 제거 : {value}")
        return default

    return str(value).strip()


def _get_recent_meeting(group_id: Optional[str] = None) -> Optional[str]:
    """최근 회의 ID 조회"""
    try:
        db = SessionLocal()
        query = db.query(Meeting).filter(Meeting.status == "completed")

        if group_id:
            query = query.filter(Meeting.chat_room_id == group_id)
        
        recent = query.order_by(Meeting.start_time.desc()).first()
        db.close()

        if recent:
            logger.info(f"자동 선택된 meeting_id : {recent.meeting_id}")
            return recent.meeting_id
        
        return None
    except Exception as e:
        logger.error(f"최근 회의 조회 실패 : {e}")
        return None

# ===================================================================
# Tool 1: 회의 목록 조회 (MongoDB 직접 조회)
# ===================================================================
@tool
def get_recent_meetings(
    group_id: Optional[str] = None,
    limit: int = 5,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    최근 회의 목록을 조회합니다.
    
    사용 시나리오:
    - "지난 회의 요약해줘"
    - "최근 회의들 보여줘"
    - "이번 주 회의 목록"
    
    Returns:
        회의 목록 (meeting_id, title, date 포함)
    """
    logger.info(f"[Tool] get_recent_meetings: group_id={group_id}, limit={limit}")
    logger.info(f"start_date = {start_date}, end_date={end_date}")
    
    try:
        
        group_id = _clean_field_value(group_id) if group_id else None
        start_date = _clean_field_value(start_date) if start_date else None
        end_date = _clean_field_value(end_date) if end_date else None

        db = SessionLocal()
        query = db.query(Meeting).filter(Meeting.status == "completed")
        
        # group_id 필터
        if group_id:
            query = query.filter(Meeting.chat_room_id == group_id)

        # 날짜 필터
        if start_date:
            query = query.filter(Meeting.start_time >= start_date)
            logger.debug(f"날짜 필터 : start >= {start_date}")

        if end_date:
            query = query.filter(Meeting.start_time <= end_date)
            logger.debug(f"날짜 필터 : end <= {end_date}")
        
        meetings = query.order_by(Meeting.start_time.desc()).limit(limit).all()
        db.close()
        
        result = []
        for m in meetings:
            result.append({
                "meeting_id": m.meeting_id,
                "title": m.title,
                "start_time": m.start_time,
                "duration_ms": m.duration_ms,
                "participant_count": m.participant_count
            })
        
        logger.info(f"회의 {len(result)}개 조회 완료")
        return result
    
    except Exception as e:
        logger.error(f"회의 목록 조회 실패: {e}", exc_info=True)
        return []


# ===================================================================
# Tool 2: 회의 요약본 조회 (MongoDB 직접)
# ===================================================================
@tool
def get_meeting_summary(
    meeting_id: str = "",
    group_id: str = ""
) -> Dict[str, Any]:
    """
    특정 회의의 요약본을 조회합니다.
    
    사용 시나리오:
    - "회의 241211_abc12 요약해줘"
    - "지난 회의 결정사항 뭐였어?"
    - "이전 회의 액션 아이템 알려줘"
    
    Returns:
        요약본 (summary_text, key_points, action_items 등)
    """
    logger.info(f"[Tool] get_meeting_summary: meeting_id={meeting_id}, group_id={group_id}")
    
    try:
        # FieldInfo 처리
        meeting_id = _clean_field_value(meeting_id) if meeting_id else None
        group_id = _clean_field_value(group_id) if group_id else None

        logger.debug(f"정제된 meeting_id: {meeting_id}, group_id: {group_id}")

        # meeting_id가 없으면 최근 회의 자동 조회
        if not meeting_id:
            logger.info("meeting_id 없음 -> 최근 회의 자동 조회")            
            meeting_id = _get_recent_meeting(group_id)

            if not meeting_id:
                return {
                    "error" : "조회 가능한 회의가 없습니다.",
                    "meeting_id" : None
                }

        # MongoDB에서 요약 조회
        mongo_db = get_mongo_db()
        mongo_service = MongoMeetingService(mongo_db)
        
        summary = mongo_service.get_summary(meeting_id)
        
        if not summary:
            return {"error": f"회의 {meeting_id}의 요약을 찾을 수 없습니다."}
        
        return {
            "meeting_id": meeting_id,
            "summary_text": summary.summary_text,
            "key_points": summary.key_points,
            "action_items": summary.action_items,
            "decisions": summary.decisions,
            "next_agenda": summary.next_agenda
        }
    
    except Exception as e:
        logger.error(f"요약 조회 실패: {e}", exc_info=True)
        return {"error": str(e)}


# ===================================================================
# Tool 3: 회의 전사본 검색 (ChromaDB 벡터 검색)
# ===================================================================
@tool
def search_meeting_transcript(
    query: str = Field(..., description="검색할 질문/키워드"),
    meeting_id: Optional[str] = Field(None, description="특정 회의에서만 검색"),
    group_id: Optional[str] = Field(None, description="특정 그룹 회의들에서 검색"),
    k: int = Field(5, description="반환할 결과 개수")
) -> List[Dict[str, Any]]:
    """
    회의 전사본에서 관련 내용을 벡터 검색합니다.
    
    사용 시나리오:
    - "API 개발 일정에 대해 누가 말했어?"
    - "디자인 관련해서 무슨 얘기 나왔어?"
    - "김철수가 언급한 내용 찾아줘"
    
    Returns:
        관련 segment 목록 (content, speaker, timestamp 포함)
    """
    
    try:
        # FieldInfo 처리
        meeting_id = _clean_field_value(meeting_id) if meeting_id else None
        group_id = _clean_field_value(group_id) if group_id else None

        vector_store = VectorStoreService()
        
        # 통합 search() 메서드 사용
        results = vector_store.search(
            query = query,
            k = k,
            meeting_id = meeting_id,
            group_id = group_id
        )
        
        segments = []
        for doc in results:
            segments.append({
                "content": doc.page_content,
                "meeting_id": doc.metadata.get("meeting_id"),
                "speaker": doc.metadata.get("speaker_name"),
                "timestamp": doc.metadata.get("timestamp_display"),
                "confidence": doc.metadata.get("confidence"),
                "type": doc.metadata.get("type", "voice")
            })
        
        logger.info(f"검색 결과 {len(segments)}개")
        return segments
    
    except Exception as e:
        logger.error(f"전사본 검색 실패: {e}", exc_info=True)
        return []


# ===================================================================
# Tool 4: 회의 전체 컨텍스트 조회
# ===================================================================
@tool
def get_meeting_context(
    meeting_id: Optional[str] = Field(None, description="조회할 회의 ID")
) -> Dict[str, Any]:
    """
    회의의 전체 컨텍스트를 조회합니다 (전사본 + 요약본).
    
    사용 시나리오:
    - "회의 241211_abc12 전체 내용 보여줘"
    - 상세한 분석이 필요한 경우
    
    Returns:
        전사본 + 요약본 통합 정보
    """
    logger.info(f"[Tool] get_meeting_context: {meeting_id}")
    
    try:
        # FieldInfo 처리
        meeting_id = _clean_field_value(meeting_id) if meeting_id else None

        # meeting_id가 없으면 최근 회의 자동 조회
        if not meeting_id:
            logger.info("  meeting_id 없음 → 최근 회의 자동 조회")
            meeting_id = _get_recent_meeting()

            if not meeting_id:
                return {"error": "조회 가능한 회의가 없습니다."}
        
        mongo_db = get_mongo_db()
        mongo_service = MongoMeetingService(mongo_db)
        
        transcript = mongo_service.get_transcript(meeting_id)
        summary = mongo_service.get_summary(meeting_id)
        
        context = {
            "meeting_id": meeting_id
        }
        
        if transcript:
            context.update({
                "title": transcript.title,
                "duration_ms": transcript.duration_ms,
                "speakers": transcript.speakers,
                "full_text": transcript.full_text[:3000]  # 토큰 제한
            })
        
        if summary:
            context.update({
                "summary": summary.summary_text,
                "key_points": summary.key_points,
                "action_items": summary.action_items
            })
        
        return context
    
    except Exception as e:
        logger.error(f"컨텍스트 조회 실패: {e}", exc_info=True)
        return {"error": str(e)}


# ===================================================================
# Tool 5: 발화자 검색
# ===================================================================
@tool
def search_by_speaker(
    speaker_name: str = Field(..., description = "발화자 이름"),
    query: Optional[str] = Field(None, description = "검색할 내용 (선택)"),
    meeting_id: Optional[str] = Field(None, description = "특정 회의로 제한"),
    group_id: Optional[str] = Field(None, description = "특정 그룹으로 제한"),
    k: int = Field(5, description = "변환 개수")
) -> List[Dict[str, Any]]:
    """
    특정 발화자의 발언을 검색합니다

    사용 시나리오:
    - "홍길동이 뭐라고 했어?"
    - "김철수가 API에 대해 한 말 찾아줘"
    """
    logger.info(f"[Tool] search_by_speaker: {speaker_name}, query={query}")

    try:
        # FieldInfo 처리
        meeting_id = _clean_field_value(meeting_id) if meeting_id else None
        group_id = _clean_field_value(group_id) if group_id else None
        query = _clean_field_value(query) if query else None

        vector_store = VectorStoreService()

        # 통합 search() 메서드 사용
        results = vector_store.search(
            query = query or "",
            k = k,
            meeting_id = meeting_id,
            group_id = group_id,
            speaker_name = speaker_name
        )

        segments = []
        for doc in results:
            segments.append({
                "content": doc.page_content,
                "speaker": doc.metadata.get("speaker_name"),
                "timestamp": doc.metadata.get("timestamp_display"),
                "meeting_id": doc.metadata.get("meeting_id"),
                "confidence": doc.metadata.get("confidence")
            })

        logger.info(f"발화자 검색 완료 : {len(segments)}개")
        return segments

    except Exception as e:
        logger.error(f"발화자 검색 실패 : {e}", exc_info=True)
        return []

# ===================================================================
# Tool List
# ===================================================================
MEETING_TOOLS = [
    get_recent_meetings,
    get_meeting_summary,
    search_meeting_transcript,
    get_meeting_context,
    search_by_speaker
]