from typing import TypedDict, List, Dict, Any, Optional
from app.services.meeting_chatbot.agent_structures import Decision, Action, Observation

class ChatbotState(TypedDict):
    """
    Agent State (Tool-Orchestrated Agent)

    Decision -> Action -> Observation -> Answer
    """

    # Input
    query: str
    meeting_id: Optional[str]
    group_id: Optional[str]

    # Agent Decision
    decision: Optional[Decision]

    # Agent Actions
    actions: List[Action]

    # Agent Observations
    observations: List[Observation]

    # 검색 결과
    relevant_segments: List[dict]
    meeting_context: Dict

    # 답변
    answer: str
    confidence: float
    sources: List[str]

    # Metadata
    search_performed: bool
    needs_more_info: bool
