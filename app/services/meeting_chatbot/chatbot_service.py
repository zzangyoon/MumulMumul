from app.core.logger import setup_logger
from app.config import settings
from langchain_openai import ChatOpenAI

from .state import ChatbotState
from .graph_builder import build_graph

logger = setup_logger(__name__)


class MeetingChatbotService:

    def __init__(self):
        logger.info("Initializing MeetingChatbotService (Tool-based) ...")

        self.llm = ChatOpenAI(
            model=settings.LLM_MODEL,
            api_key=settings.OPENAI_API_KEY,
            temperature=0.3
        )

        # Tool 기반 Graph 빌드 (vector_store, mongo_service 불필요)
        self.graph = build_graph(llm=self.llm)

        logger.info("MeetingChatbotService initialized")

    async def ask(
        self, query: str, 
        meeting_id: str = None,
        group_id: str = None
    ) -> dict:
        logger.info(f"질문 처리: {query}")

        initial_state: ChatbotState = {
            "query": query,
            "meeting_id": meeting_id,
            "group_id": group_id,

            # Tool 관련
            "tool_calls": [],
            "tool_results": [],
            "agent_response": None,

            "relevant_segments": [],
            "meeting_context": {},

            "answer": "",
            "confidence": 0.0,
            "sources": [],

            "search_performed": False,
            "needs_more_info": False
        }

        final_state = await self.graph.ainvoke(initial_state)

        # Tool 실행 정보 추가
        tool_info = []
        for result in final_state.get("tool_results", []):
            tool_info.append({
                "tool" : result["tool_name"],
                "args" : result["tool_args"]
            })

        return {
            "answer": final_state["answer"],
            "confidence": final_state["confidence"],
            "sources": final_state["sources"],
            "tool_used" : tool_info,
            "relevant_segments": final_state.get("relevant_segments", [])
        }
