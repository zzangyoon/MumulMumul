from app.core.logger import setup_logger
from app.config import settings
from langchain_openai import ChatOpenAI
from .state import ChatbotState
from .graph_builder import build_graph
from .agent_structures import AgentTrace
import time

logger = setup_logger(__name__)


class MeetingChatbotService:
    """
    Tool-Orchestrated Agent 기반 회의 챗봇 서비스

    Decision -> Action -> Observation
    """

    def __init__(self):
        logger.info("Initializing MeetingChatbotService (Tool-Orchestrated Agent) ...")

        self.llm = ChatOpenAI(
            model=settings.LLM_MODEL,
            api_key=settings.OPENAI_API_KEY,
            temperature=0.3
        )

        # Agent Graph 빌드
        self.graph = build_graph(llm=self.llm)

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

        try:
            # Agent Graph 실행
            final_state = await self.graph.ainvoke(initial_state)

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
                "relevant_segments": final_state.get("relevant_segments", [])
            }
            return response
        
        except Exception as e:
            logger.error(f"[AGENT ERROR] {e}", exc_info=True)

            return {
                "answer": f"처리 중 오류가 발생했습니다: {str(e)}",
                "confidence": 0.0,
                "sources": [],
                "trace": None,
                "relevant_segments": []
            }
