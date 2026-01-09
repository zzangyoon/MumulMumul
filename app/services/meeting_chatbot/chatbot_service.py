from app.core.logger import setup_logger
from app.config import settings
from langchain_openai import ChatOpenAI
from .state import ChatbotState
from .graph_builder import build_graph
from .graph_builder_llm import build_graph_llm
from .agent_structures import AgentTrace
from .semantic_cache import get_semantic_cache
import time
import os

logger = setup_logger(__name__)

# LangSmith 환경변수 설정
if settings.LANGCHAIN_API_KEY:
    os.environ["LANGCHAIN_TRACING_V2"] = str(settings.LANGCHAIN_TRACING_V2).lower()
    os.environ["LANGCHAIN_ENDPOINT"] = settings.LANGCHAIN_ENDPOINT
    os.environ["LANGCHAIN_API_KEY"] = settings.LANGCHAIN_API_KEY
    os.environ["LANGCHAIN_PROJECT"] = settings.LANGCHAIN_PROJECT
    logger.info(f"LangSmith enabled: {settings.LANGCHAIN_PROJECT}")


class MeetingChatbotService:
    """
    회의 챗봇 서비스

    mode:
    - "rule": 규칙 기반 (기존, 빠름)
    - "llm": LLM 기반 (새로운, 정확함)

    rule mode:
        Tool-Orchestrated Agent 기반 회의 챗봇 서비스
        Decision -> Action -> Observation
        테스트용 : __init__() 에서 mode: str = "rule" 로 변경해서 테스트
    """

    def __init__(self, mode: str = "llm"):
        logger.info("Initializing MeetingChatbotService (mode={mode} ...")

        self.mode = mode

        self.llm = ChatOpenAI(
            model=settings.LLM_MODEL,
            api_key=settings.OPENAI_API_KEY,
            temperature=0.3
        )

        # 모드에 따라 Graph 선택
        if mode == "llm":
            self.graph = build_graph_llm(llm=self.llm)
            logger.info("LLM 기반 Agent Graph 초기화")
        else:
            self.graph = build_graph(llm=self.llm)
            logger.info("규칙 기반 Agent Graph 초기화")

        logger.info("MeetingChatbotService initialized")

    async def ask(
        self,
        query: str, 
        meeting_id: str = None,
        group_id: str = None
    ) -> dict:
        """
        Agent에게 질문
        """

        logger.info(f"질문 처리: {query}")

        start_time = time.time()

        initial_state: ChatbotState = {
            "query": query,
            "meeting_id": meeting_id,
            "group_id": group_id,

            # Agent 구조
            "decision": None,
            "actions": [],
            "observations": [],

            # 결과
            "answer": "",
            "confidence": 0.0,
            "sources": [],

            "relevant_segments": [],
            "meeting_context": {},
            "search_performed": False,
            "needs_more_info": False
        }

        # LangSmith config (트레이싱용)
        config = {
            "run_name": f"[{self.mode}] {query[:50]}",
            "metadata": {
                "mode": self.mode,
                "meeting_id": meeting_id,
                "group_id": group_id
            },
            "tags": [self.mode, "meeting-chatbot"]
        }

        try:
            # Agent Graph 실행
            final_state = await self.graph.ainvoke(initial_state, config=config)

            total_duration = int((time.time() - start_time) * 1000)

            # AgentTrace 생성
            trace = AgentTrace(
                query = query,
                decision = final_state.get("decision"),
                actions = final_state.get("actions", []),
                observations = final_state.get("observations", []),
                answer = final_state["answer"],
                confidence = final_state["confidence"],
                total_duration_ms = total_duration
            )

            logger.info("[AGENT COMPLETE]")
            logger.info(trace.get_summary())

            # 응답 구성
            response = {
                "answer": final_state["answer"],
                "confidence": final_state["confidence"],
                "sources": final_state.get("sources", []),
                "trace": trace.to_dict(),
                "relevant_segments": final_state.get("relevant_segments", []),
                "mode": self.mode
            }
            return response
        
        except Exception as e:
            logger.error(f"[AGENT ERROR] {e}", exc_info=True)

            return {
                "answer": f"처리 중 오류가 발생했습니다: {str(e)}",
                "confidence": 0.0,
                "sources": [],
                "trace": None,
                "relevant_segments": [],
                "mode": self.mode
            }

    def get_cache_stats(self) -> dict:
        """캐시 통계 반환"""
        cache = get_semantic_cache()
        return cache.get_stats()

    def clear_cache(self):
        """캐시 전체 삭제"""
        cache = get_semantic_cache()
        cache.clear()
