from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from datetime import datetime
from enum import Enum


class IntentType(Enum):
    """Agent가 인식하는 의도 타입"""
    GET_RECENT_MEETINGS = "get_recent_meetings"
    GET_MEETING_SUMMARY = "get_meeting_summary"
    SEARCH_TRANSCRIPT = "search_transcript"
    SEARCH_BY_SPEAKER = "search_by_speaker"
    GET_MEETING_CONTEXT = "get_meeting_context"
    UNKNOWN = "unknown"


@dataclass
class Decision:
    """
    Agent의 결정 (Decision)

    ToolSelector가 분석한 결과를 구조화
    """

    intent: str
    confidence: float
    entities: Dict[str, Any] = field(default_factory = dict)
    reasoning: str = ""
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any] :
        return {
            "intent" : self.intent,
            "confidence" : self.confidence,
            "entities" : self.entities,
            "reasoning" : self.reasoning,
            "timestamp" : self.timestamp
        }
    
    def __repr__(self):
        return (
            f"Decision(intent={self.intent}, "
            f"confidence={self.confidence:.2f}, "
            f"entities={self.entities})"
        )
    

@dataclass
class Action:
    """
    Agent의 행동 (Action)

    실제로 실행할 Tool과 인자
    """
    tool_name: str
    tool_args: Dict[str, Any] = field(default_factory = dict)
    timestamp: str = field(default_factory = lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name" : self.tool_name,
            "tool_args" : self.tool_args,
            "timestamp" : self.timestamp
        }
    
    def __repr__(self):
        return f"Action(tool={self.tool_name}, args={self.tool_args})"
    

@dataclass
class Observation:
    """
    Agent의 관찰 (Observation)

    Action 실행 결과
    """
    action: Action
    result: Any
    success: bool
    error: Optional[str] = None
    duration_ms: int = 0
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action.to_dict(),
            "result": self.result if self.success else None,
            "success": self.success,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp
        }
    
    def __repr__(self):
        status = "O" if self.success else "X"
        return (
            f"Observation({status} {self.action.tool_name}, "
            f"duration={self.duration_ms}ms)"
        )
    

@dataclass
class AgentTrace:
    """
    Agent 실행 전체 추적

    Decision -> Actions -> Observations -> Answer
    """
    query: str
    decision: Optional[Decision] = None
    actions: List[Action] = field(default_factory=list)
    observations: List[Observation] = field(default_factory=list)
    answer: str = ""
    confidence: float = 0.0
    total_duration_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "decision": self.decision.to_dict() if self.decision else None,
            "actions": [a.to_dict() for a in self.actions],
            "observations": [o.to_dict() for o in self.observations],
            "answer": self.answer,
            "confidence": self.confidence,
            "total_duration_ms": self.total_duration_ms
        }
    
    def add_action(self, action: Action):
        """Action 추가"""
        self.actions.append(action)
    
    def add_observation(self, observation: Observation):
        """Observation 추가"""
        self.observations.append(observation)
    
    def get_summary(self) -> str:
        """실행 요약"""
        success_count = sum(1 for o in self.observations if o.success)
        return (
            f"Query: {self.query}\n"
            f"Decision: {self.decision.intent if self.decision else 'None'}\n"
            f"Actions: {len(self.actions)}\n"
            f"Success: {success_count}/{len(self.observations)}\n"
            f"Duration: {self.total_duration_ms}ms"
        )