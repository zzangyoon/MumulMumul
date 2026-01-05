from langchain_core.prompts import ChatPromptTemplate
from app.core.logger import setup_logger
from app.core.db import SessionLocal
from app.core.schemas import Meeting
from app.services.meeting_chatbot.decision_maker import DecisionMaker
from app.services.meeting_chatbot.tool_selector import ToolSelector
from app.services.meeting_chatbot.tools import MEETING_TOOLS
from app.services.meeting_chatbot.agent_structures import Decision, Action, Observation
import time


logger = setup_logger(__name__)


# -----------------------------------------------------------
# Node 1 : Decision Making (Agent의 사고)
# -----------------------------------------------------------
async def agent_decide(state, llm):
    """
    Agent의 Decision Making

    Query -> Decisin (Intent + Entities)
    """
    query = state["query"]
    meeting_id = state.get("meeting_id")
    group_id = state.get("group_id")

    logger.info(f"[Node] agent_decide: {query}")
    logger.info(f"  meeting_id: {meeting_id}, group_id: {group_id}")

    try:
        # DecisionMaker로 Decision 생성
        decisions = await DecisionMaker.make_multi_decisions(
            query, meeting_id, group_id, llm
        )

        if not decisions:
            logger.warnging("Decision 생성 실패")
            state["answer"] = "죄송합니다. 질문을 이해하지 못했습니다."
            state["confidence"] = 0.0
            return state
        
        # 첫 번째 Decision 저장 (main decision)
        main_decision = decisions[0]
        state["decision"] = main_decision

        # Decision 로깅
        logger.info("[DECISION MADE]")
        logger.info(f"  Intent: {main_decision.intent}")
        logger.info(f"  Confidence: {main_decision.confidence:.2f}")
        logger.info(f"  Entities: {main_decision.entities}")
        logger.info(f"  Reasoning: {main_decision.reasoning}")
        logger.info("="*60)

        # Decision -> Action 변환
        actions = []
        for decision in decisions:
            action = Action(
                tool_name = decision.intent,
                tool_args = decision.entities.copy()
            )
            actions.append(action)

        state["actions"] = actions

        logger.info(f"[ACTIONS PLANNED] {len(actions)} actions")
        for i, action in enumerate(actions, 1):
            logger.info(f"{i}. {action.tool_name}({action.tool_args})")

        return state

    except Exception as e:
        logger.error(f"Decision 실패 : {e}", exc_info = True)
        state["answer"] = f"결정 중 오류 발생 : {str(e)}"
        state["confidence"] = 0.0
        return state


# -----------------------------------------------------------
# Node 2 : Action Execution (Agent 의 행동)
# -----------------------------------------------------------
async def execute_actions(state):
    """
    Agent의 Action 수행

    Actions -> Observations
    """
    actions = state.get("actions", [])

    if not actions:
        logger.warning("실행할 Action이 없습니다")
        return state
    
    logger.info(f"[Node] execute_actions: {len(actions)}개 실행")

    observations = []
    meeting_id_from_first = None

    for i, action in enumerate(actions, 1):

        start_time = time.time()

        try:
            # 이전 Action 결과에서 meeting_id 전달
            tool_args = action.tool_args.copy()

            if meeting_id_from_first and "meeting_id" not in tool_args:
                if action.tool_name in ["get_meeting_summary", "get_meeting_context", "search_meeting_transcript"]:
                    tool_args["meeting_id"] = meeting_id_from_first
                    logger.info(f"  → meeting_id 자동 전달: {meeting_id_from_first}")

            # Tool 찾기
            tool_func = next(
                (t for t in MEETING_TOOLS if t.name == action.tool_name),
                None
            )

            if not tool_func:
                raise ValueError(f"Tool not found : {action.tool_name}")
            
            # Tool 실행
            result = tool_func.invoke(tool_args)
            duration_ms = int((time.time() - start_time) * 1000)

            # 첫 번째 Action이 get_recent_meetings인 경우 meeting_id 추출
            if action.tool_name == "get_recent_meetings" and isinstance(result, list) and result:
                meeting_id_from_first = result[0].get("meeting_id")
                logger.info(f"추출된 meeting_id: {meeting_id_from_first}")

            observation = Observation(
                action=action,
                result=result,
                success=True,
                duration_ms=duration_ms
            )

            logger.info(f"Success : {duration_ms}ms")

            if isinstance(result, list):
                logger.info(f" {len(result)} items")
            elif isinstance(result, dict):
                logger.info(f"keys : {list(result.keys())}")

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)

            observation = Observation(
                action = action,
                result = None,
                success = False,
                error = str(e),
                duration_ms = duration_ms
            )

            logger.error(f" X Failed ({duration_ms}ms) : {e}")

        observations.append(observation)

    state["observations"] = observations

    # 성공/실패 통계
    success_count = sum(1 for o in observations if o.success)
    total_duration = sum(o.duration_ms for o in observations)

    logger.info("[EXECUTION SUMMARY]")
    logger.info(f"  Total: {len(observations)} actions")
    logger.info(f"  Success: {success_count}")
    logger.info(f"  Failed: {len(observations) - success_count}")
    logger.info(f"  Duration: {total_duration}ms")
    logger.info("="*60)
    return state


# -----------------------------------------------------------
# Node 3 : Response Generation (Agent의 답변)
# -----------------------------------------------------------
async def generate_final_answer(state, llm):

    """
    Agent의 최종 답변 생성

    Observations -> Answer
    """
    query = state["query"]
    decision = state.get("decision")
    observations = state.get("observations", [])

    logger.info(f"[Node] generate_final_answer")

    # Agent 없이 이미 답변이 생성된 경우
    if state.get("answer") and not observations:
        logger.info("이미 답변이 생성됨 (Decision 단계)")
        return state

    # 최적화 : 단순 요약 요청인지 판단
    if _is_simple_summary_request(observations, query):
        logger.info("단순 요약 요청 -> LLM 생략, 직접 반환")
        return _direct_summary_response(state, observations)
    
    # 복잡한 질문 -> LLM 사용
    logger.info("복잡한 질문 -> LLM 답변 생성")
    return await _llm_based_response(state, observations, query, llm)


# -----------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------
def _is_simple_summary_request(observations: list, query: str) -> bool:
    """
    단순 요약본 요청인지 판단
    """

    # Tool 1개만 실행?
    if len(observations) != 1:
        return False
    
    obs = observations[0]
    if not obs.success:
        return False
    
    tool_name = obs.action.tool_name
    if tool_name not in ["get_meeting_summary", "get_meeting_context"]:
        return False

    query_lower = query.lower()
    simple_patterns = ["요약", "정리", "알려줘", "보여줘", "뭐였어", "뭐야"]

    return any(p in query_lower for p in simple_patterns)

    
# -----------------------------------------------------------
# 직접 반환 (LLM 생략)
# -----------------------------------------------------------
def _direct_summary_response(state: dict, observations: list) -> dict:
    """
    MongoDB 요약본을 직접 반환 (LLM 생략)
    """
    obs = observations[0]
    data = obs.result

    if "error" in data:
        state["answer"] = f"죄송합니다. {data['error']}"
        state["confidence"] = 0.0
        state["sources"] = []
        return state
    
    tool_name = obs.action.tool_name
    
    # get_meeting_summary 포맷팅
    if tool_name == "get_meeting_summary":
        answer_parts = []
        
        # 요약
        if data.get("summary_text"):
            answer_parts.append(f"**회의 요약**\n{data['summary_text']}")
        
        # 핵심 포인트
        if data.get("key_points"):
            answer_parts.append("\n\n**핵심 포인트**")
            for i, kp in enumerate(data["key_points"], 1):
                answer_parts.append(f"{i}. {kp}")
        
        # 액션 아이템
        if data.get("action_items"):
            answer_parts.append("\n\n**액션 아이템**")
            for i, ai in enumerate(data["action_items"], 1):
                answer_parts.append(f"{i}. {ai}")
        
        # 결정 사항
        if data.get("decisions"):
            answer_parts.append("\n\n**결정 사항**")
            for i, d in enumerate(data["decisions"], 1):
                answer_parts.append(f"{i}. {d}")
        
        # 다음 안건
        if data.get("next_agenda"):
            answer_parts.append("\n\n**다음 안건**")
            for i, na in enumerate(data["next_agenda"], 1):
                answer_parts.append(f"{i}. {na}")
        
        state["answer"] = "\n".join(answer_parts)
        state["confidence"] = 1.0  # 직접 반환이므로 100% 신뢰도
        state["sources"] = [data["meeting_id"]]
        
        logger.info("요약본 직접 반환 완료")

    # get_meeting_context 직접 포맷팅
    elif tool_name == "get_meeting_context":
        answer_parts = []
        
        if data.get("title"):
            answer_parts.append(f"**회의 제목**: {data['title']}")
        
        if data.get("summary"):
            answer_parts.append(f"\n**요약**\n{data['summary']}")
        
        if data.get("key_points"):
            answer_parts.append("\n**핵심 포인트**")
            for i, kp in enumerate(data["key_points"], 1):
                answer_parts.append(f"{i}. {kp}")
        
        state["answer"] = "\n".join(answer_parts)
        state["confidence"] = 1.0
        state["sources"] = [data["meeting_id"]]
        
        logger.info("컨텍스트 직접 반환 완료")
    
    return state


# -----------------------------------------------------------
# LLM 기반 답변 (복잡한 질문)
# -----------------------------------------------------------
async def _llm_based_response(state: dict, observations: list, query: str, llm) -> dict:
    """
    LLM 기반 답변 생성
    """

    # Observation 결과 정리
    tool_context = ""
    sources = []
    
    for obs in observations:
        tool_name = obs.action.tool_name
        
        tool_context += f"\n\n[{tool_name} 결과]:\n"
        
        if not obs.success:
            tool_context += f"오류: {obs.error}\n"
            continue
        
        data = obs.result

        # 결과 포맷팅
        if tool_name == "get_recent_meetings":
            for meeting in data[:3]:
                tool_context += f"- {meeting['title']} ({meeting['meeting_id']})\n"
                tool_context += f"  시작: {meeting['start_time']}\n"
                sources.append(meeting['meeting_id'])
        
        elif tool_name == "get_meeting_summary":
            tool_context += f"요약: {data['summary_text']}\n"
            if data.get('key_points'):
                tool_context += "\n핵심 포인트:\n"
                for kp in data['key_points'][:5]:
                    tool_context += f"  - {kp}\n"
            sources.append(data['meeting_id'])
        
        elif tool_name == "search_meeting_transcript":
            for seg in data[:5]:
                tool_context += f"- [{seg['timestamp']}] [{seg['speaker']}] {seg['content'][:150]}...\n"
                if seg.get('meeting_id'):
                    sources.append(seg['meeting_id'])
        
        elif tool_name == "search_by_speaker":
            for seg in data[:5]:
                tool_context += f"- [{seg.get('timestamp', '')}] {seg.get('content', '')[:150]}...\n"
                if seg.get('meeting_id'):
                    sources.append(seg['meeting_id'])

        elif tool_name == "get_meeting_context":
            tool_context += f"제목: {data.get('title', 'N/A')}\n"
            tool_context += f"요약: {data.get('summary', 'N/A')[:300]}...\n"
            sources.append(data.get('meeting_id'))
    
    # 답변 생성 프롬프트
    prompt = ChatPromptTemplate.from_messages([
        ("system", """
        당신은 회의 요약 전문 어시스턴트입니다.
        제공된 정보만을 기반으로 정확하고 간결하게 답변하세요.
        불확실한 내용은 추측하지 말고, "정보가 없습니다"라고 말하세요.
        
        답변 가이드:
        - 자연스럽고 친절한 톤
        - 구조화된 정보는 목록으로 제시
        - 중요한 내용은 강조"""),
        
        ("human", """
        질문: {query}

        조회된 정보:
        {tool_context}

        위 정보를 기반으로 사용자의 질문에 답변해주세요.""")
    ])
    
    chain = prompt | llm
    
    try:
        response = await chain.ainvoke({
            "query": query,
            "tool_context": tool_context
        })
        
        state["answer"] = response.content
        state["confidence"] = 0.9 if len(observations) >= 2 else 0.7
        state["sources"] = list(set(sources))
        
        logger.info("LLM 답변 생성 완료")
    
    except Exception as e:
        logger.error(f"답변 생성 실패: {e}", exc_info=True)
        state["answer"] = "답변 생성 중 오류가 발생했습니다."
        state["confidence"] = 0.0
        state["sources"] = []
    
    return state


# -----------------------------------------------------------
# 조건 분기 함수
# -----------------------------------------------------------
def should_execute_actions(state) -> str:
    """Action 실행 여부 결정"""
    if state.get("actions"):
        return "execute_actions"
    else:
        return "end"