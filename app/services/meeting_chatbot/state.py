from typing import TypedDict, List, Dict, Any, Optional

class ChatbotState(TypedDict):
    query: str
    meeting_id: Optional[str]
    group_id: Optional[str]

    # Tool 관련
    tool_calls: List[Dict[str, Any]]    # LLM이 선택한 Tool 목록
    tool_results: List[Dict[str, Any]]  # Tool 실행 결과
    agent_response: Optional[Any]       # LLM의 원본 응답

    # 검색 결과
    relevant_segments: List[dict]
    meeting_context: Dict

    # 답변
    answer: str
    confidence: float
    sources: List[str]

    search_performed: bool
    needs_more_info: bool
