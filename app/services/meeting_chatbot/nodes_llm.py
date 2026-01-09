"""
LLM 기반 Agent Nodes

기존 nodes.py(규칙 기반)와 별도로 운영
"""

from langchain_core.prompts import ChatPromptTemplate
from app.core.logger import setup_logger
from app.services.meeting_chatbot.decision_maker_llm import LLMDecisionMaker
from app.services.meeting_chatbot.tools import MEETING_TOOLS
from app.services.meeting_chatbot.agent_structures import Action, Observation
import time

logger = setup_logger(__name__)


# -----------------------------------------------------------
# Node 1 : LLM Decision Making
# -----------------------------------------------------------
async def agent_decide_llm(state, llm):
    """
    LLM 기반 Decision Making
    
    Query → LLM Router → Decisions
    """
    query = state["query"]
    meeting_id = state.get("meeting_id")
    group_id = state.get("group_id")

    logger.info(f"[Node] agent_decide_llm: {query}")

    try:
        # LLM으로 Decision 생성
        decisions = await LLMDecisionMaker.make_decision(
            query, meeting_id, group_id, llm
        )

        if not decisions:
            logger.warning("Decision 생성 실패")
            state["answer"] = "죄송합니다. 질문을 이해하지 못했습니다."
            state["confidence"] = 0.0
            return state

        # 첫 번째 Decision 저장
        main_decision = decisions[0]
        state["decision"] = main_decision

        logger.info(f"[LLM DECISION]")
        logger.info(f"  Intent: {main_decision.intent}")
        logger.info(f"  Confidence: {main_decision.confidence:.2f}")
        logger.info(f"  Entities: {main_decision.entities}")

        # Decision → Action 변환
        actions = []
        for decision in decisions:
            action = Action(
                tool_name=decision.intent,
                tool_args=decision.entities.copy()
            )
            actions.append(action)

        state["actions"] = actions

        logger.info(f"[ACTIONS] {len(actions)}개 계획됨")
        for i, action in enumerate(actions, 1):
            logger.info(f"  {i}. {action.tool_name}({action.tool_args})")

        return state

    except Exception as e:
        logger.error(f"LLM Decision 실패: {e}", exc_info=True)
        state["answer"] = f"결정 중 오류 발생: {str(e)}"
        state["confidence"] = 0.0
        return state


# -----------------------------------------------------------
# Node 2 : Action Execution (기존과 동일)
# -----------------------------------------------------------
async def execute_actions_llm(state):
    """
    Action 실행 (기존 execute_actions와 동일)
    """
    actions = state.get("actions", [])

    if not actions:
        logger.warning("실행할 Action 없음")
        return state

    logger.info(f"[Node] execute_actions_llm: {len(actions)}개")

    observations = []
    meeting_id_from_first = None

    for i, action in enumerate(actions, 1):
        start_time = time.time()

        try:
            tool_args = action.tool_args.copy()

            # 이전 Action에서 meeting_id 전달
            if meeting_id_from_first and "meeting_id" not in tool_args:
                if action.tool_name in ["get_meeting_summary", "get_meeting_context", "search_meeting_transcript", "search_by_speaker"]:
                    tool_args["meeting_id"] = meeting_id_from_first
                    logger.info(f"  → meeting_id 자동 전달: {meeting_id_from_first}")

            # Tool 찾기
            tool_func = next(
                (t for t in MEETING_TOOLS if t.name == action.tool_name),
                None
            )

            if not tool_func:
                raise ValueError(f"Tool not found: {action.tool_name}")

            # Tool 실행
            result = tool_func.invoke(tool_args)
            duration_ms = int((time.time() - start_time) * 1000)

            # get_recent_meetings에서 meeting_id 추출
            if action.tool_name == "get_recent_meetings" and isinstance(result, list) and result:
                meeting_id_from_first = result[0].get("meeting_id")
                logger.info(f"  추출된 meeting_id: {meeting_id_from_first}")

            observation = Observation(
                action=action,
                result=result,
                success=True,
                duration_ms=duration_ms
            )
            logger.info(f"  ✓ {action.tool_name}: {duration_ms}ms")

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            observation = Observation(
                action=action,
                result=None,
                success=False,
                error=str(e),
                duration_ms=duration_ms
            )
            logger.error(f"  ✗ {action.tool_name}: {e}")

        observations.append(observation)

    state["observations"] = observations

    # 통계
    success_count = sum(1 for o in observations if o.success)
    total_duration = sum(o.duration_ms for o in observations)
    logger.info(f"[EXECUTION] {success_count}/{len(observations)} 성공, {total_duration}ms")

    return state


# -----------------------------------------------------------
# Node 3 : LLM Response Generation
# -----------------------------------------------------------
async def generate_final_answer_llm(state, llm):
    """
    LLM 기반 최종 답변 생성
    
    항상 LLM을 사용하여 자연스러운 답변 생성
    """
    query = state["query"]
    observations = state.get("observations", [])

    logger.info(f"[Node] generate_final_answer_llm")

    # 이미 답변이 있는 경우 (에러 등)
    if state.get("answer") and not observations:
        return state

    # Observation 결과 정리
    tool_results = []
    sources = []

    for obs in observations:
        tool_name = obs.action.tool_name
        
        if not obs.success:
            tool_results.append(f"[{tool_name}] 오류: {obs.error}")
            continue

        data = obs.result

        if isinstance(data, dict) and "error" in data:
            tool_results.append(f"[{tool_name}] {data['error']}")
            continue

        # Tool별 결과 포맷팅
        if tool_name == "get_recent_meetings":
            if isinstance(data, list) and data:
                meetings_text = []
                for m in data[:5]:
                    meetings_text.append(
                        f"- {m.get('title', 'N/A')} ({m.get('meeting_id')})\n"
                        f"  시작: {m.get('start_time', 'N/A')}"
                    )
                    if m.get('meeting_id'):
                        sources.append(m['meeting_id'])
                tool_results.append(f"[회의 목록]\n" + "\n".join(meetings_text))
            else:
                tool_results.append("[회의 목록] 조회된 회의가 없습니다.")

        elif tool_name == "get_meeting_summary":
            parts = []
            if data.get('summary_text'):
                parts.append(f"요약: {data['summary_text']}")
            if data.get('key_points'):
                parts.append("핵심 포인트:\n" + "\n".join(f"- {kp}" for kp in data['key_points'][:5]))
            if data.get('action_items'):
                parts.append("액션 아이템:\n" + "\n".join(f"- {ai}" for ai in data['action_items'][:5]))
            if data.get('decisions'):
                parts.append("결정 사항:\n" + "\n".join(f"- {d}" for d in data['decisions'][:5]))
            
            tool_results.append(f"[회의 요약]\n" + "\n\n".join(parts))
            if data.get('meeting_id'):
                sources.append(data['meeting_id'])

        elif tool_name == "search_meeting_transcript":
            if isinstance(data, list) and data:
                segments_text = []
                for seg in data[:5]:
                    segments_text.append(
                        f"- [{seg.get('speaker', 'N/A')}] {seg.get('content', '')[:200]}"
                    )
                    if seg.get('meeting_id'):
                        sources.append(seg['meeting_id'])
                tool_results.append(f"[검색 결과]\n" + "\n".join(segments_text))
            else:
                tool_results.append("[검색 결과] 관련 내용을 찾지 못했습니다.")

        elif tool_name == "search_by_speaker":
            if isinstance(data, list) and data:
                segments_text = []
                for seg in data[:5]:
                    segments_text.append(
                        f"- [{seg.get('timestamp', '')}] {seg.get('content', '')[:200]}"
                    )
                    if seg.get('meeting_id'):
                        sources.append(seg['meeting_id'])
                tool_results.append(f"[발화자 검색]\n" + "\n".join(segments_text))
            else:
                tool_results.append("[발화자 검색] 해당 발화자의 발언을 찾지 못했습니다.")

        elif tool_name == "get_meeting_context":
            parts = []
            if data.get('title'):
                parts.append(f"제목: {data['title']}")
            if data.get('summary'):
                parts.append(f"요약: {data['summary'][:500]}")
            if data.get('key_points'):
                parts.append("핵심 포인트:\n" + "\n".join(f"- {kp}" for kp in data['key_points'][:5]))
            
            tool_results.append(f"[회의 컨텍스트]\n" + "\n".join(parts))
            if data.get('meeting_id'):
                sources.append(data['meeting_id'])

    # Tool 결과가 없는 경우
    if not tool_results:
        state["answer"] = "죄송합니다. 요청하신 정보를 찾을 수 없습니다."
        state["confidence"] = 0.0
        state["sources"] = []
        return state

    # LLM으로 최종 답변 생성
    prompt = ChatPromptTemplate.from_messages([
        ("system", """당신은 회의 정보를 안내하는 친절한 어시스턴트입니다.

        규칙:
        1. 제공된 정보만 사용하여 답변하세요
        2. 정보가 없으면 "정보가 없습니다"라고 답변하세요
        3. 자연스럽고 간결하게 답변하세요
        4. 목록은 bullet point로 정리하세요
        5. 추측하지 마세요"""
        ),
        
        ("human", """사용자 질문: {query}

        조회된 정보:
        {tool_results}

        위 정보를 바탕으로 사용자의 질문에 답변해주세요."""
        )
    ])

    chain = prompt | llm

    try:
        response = await chain.ainvoke({
            "query": query,
            "tool_results": "\n\n".join(tool_results)
        })

        state["answer"] = response.content
        state["confidence"] = 0.85
        state["sources"] = list(set(sources))

        logger.info("LLM 답변 생성 완료")

    except Exception as e:
        logger.error(f"답변 생성 실패: {e}", exc_info=True)
        # Fallback: Tool 결과 직접 반환
        state["answer"] = "\n\n".join(tool_results)
        state["confidence"] = 0.6
        state["sources"] = list(set(sources))

    return state


# -----------------------------------------------------------
# 조건 분기 함수
# -----------------------------------------------------------
def should_execute_actions_llm(state) -> str:
    """Action 실행 여부 결정"""
    if state.get("actions"):
        return "execute_actions"
    else:
        return "end"
