from langchain_core.prompts import ChatPromptTemplate
from app.core.logger import setup_logger
from app.core.db import SessionLocal
from app.core.schemas import Meeting
from app.services.meeting_chatbot.tool_selector import ToolSelector
from app.services.meeting_chatbot.tools import MEETING_TOOLS


logger = setup_logger(__name__)


# -----------------------------------------------------------
# 1) Tool 선택 및 실행
# -----------------------------------------------------------
async def agent_decide(state, llm):
    """
    하이브리드 방식으로 Tool을 선택합니다.
    1. 규칙 기반 시도 (90%)
    2. 실패시 LLM 사용 (10%)
    """
    query = state["query"]
    meeting_id = state.get("meeting_id")
    group_id = state.get("group_id")

    logger.info(f"[Node] agent_decide: {query}")
    logger.info(f"  meeting_id: {meeting_id}, group_id: {group_id}")

    # 하이브리드 Tool 선택
    tools = await ToolSelector.select_multiple_tools(
        query, meeting_id, group_id, llm
    )

    if tools:
        tool_calls = []
        for tool_name, tool_args, confidence in tools:
            tool_calls.append({
                "name" : tool_name,
                "args" : tool_args,
                "confidence" : confidence
            })
        state["tool_calls"] = tool_calls
        logger.info(f"Tool 선택 완료 : {len(tool_calls)}개")

    else:
        # Tool 선택 실패
        state["answer"] = "죄송합니다. 질문을 이해하지 못했습니다."
        state["confidence"] = 0.0
        state["sources"] = []
        state["tool_calls"] = []
    
    return state


# -----------------------------------------------------------
# 2) Tool 실행 결과 수집
# -----------------------------------------------------------
async def execute_tools(state):
    """
    선택된 Tool들을 실행하고 결과를 수집합니다.
    """
    tool_calls = state.get("tool_calls", [])

    if not tool_calls:
        return state
    
    logger.info(f"[Node] execute_tools: {len(tool_calls)}개 실행")

    tool_results = []
    meeting_id_from_first_tool = None

    for i, tool_call in enumerate(tool_calls):
        tool_name = tool_call["name"]
        tool_args = tool_call["args"].copy()

        # 이전 tool 결과 다음 tool에 전달
        if meeting_id_from_first_tool and "meeting_id" not in tool_args:
            if tool_name in ["get_meeting_summary", "get_meeting_context", "search_meeting_transcript"]:
                tool_args["meeting_id"] = meeting_id_from_first_tool
                logger.info(f"meeting_id 자동 전달: {meeting_id_from_first_tool}")

        logger.info(f"[{i+1}/{len(tool_calls)}] 실행: {tool_name}({tool_args})")

        try:
            tool_func = next(
                (t for t in MEETING_TOOLS if t.name == tool_name),
                None
            )

            if tool_func:
                result = tool_func.invoke(tool_args)

                # 첫번째 tool이 get_recent_meetings인 경우 meeting_id 추출
                if tool_name == "get_recent_meetings" and isinstance(result, list) and result:
                    meeting_id_from_first_tool = result[0].get("meeting_id")
                    logger.info(f"추출된 meeting_id: {meeting_id_from_first_tool}")

                tool_results.append({
                    "tool_name" : tool_name,
                    "tool_args" : tool_args,
                    "result" : result
                })
                logger.info(f"완료 : {tool_name}")
            else:
                logger.error(f"Tool not found : {tool_name}")

        except Exception as e:
            logger.error(f"Tool 실행 실패: {tool_name} - {e}", exc_info=True)
            tool_results.append({
                "tool_name": tool_name,
                "tool_args": tool_args,
                "result": {"error": str(e)}
            })
    
    state["tool_results"] = tool_results
    logger.info(f"Tool 실행 완료 : {len(tool_results)}개 결과")

    return state


# -----------------------------------------------------------
# 3) 최종 답변 생성
# -----------------------------------------------------------
async def generate_final_answer(state, llm):
    """
    Tool 실행 결과를 기반으로 최종 답변을 생성합니다.

    최적화:
    - 단순 요약 요청 -> MongoDB 결과 직접 반환 (LLM 생략)
    - 복잡한 질문 -> LLM으로 답변 생성
    """
    query = state["query"]
    tool_results = state.get("tool_results", [])

    # Tool 없이 이미 답변이 생성된 경우
    if state.get("answer") and not tool_results:
        return state
    
    logger.info(f"[Node] generate_final_answer")

    # 최적화 : 단순 요약 요청인지 판단
    if _is_simple_summary_request(tool_results, query):
        logger.info("단순 요약 요청 → LLM 생략, 직접 반환")
        return _direct_summary_response(state, tool_results)
    
    # 복잡한 질문 -> LLM 사용
    logger.info("복잡한 질문 → LLM 답변 생성")
    return await _llm_based_response(state, tool_results, query, llm)


# -----------------------------------------------------------
# 단순 요약 요청 판단
# -----------------------------------------------------------
def _is_simple_summary_request(tool_results: list, query: str) -> bool:
    """
    단순 요약본 요청인지 판단
    
    조건:
    1. Tool이 1개만 실행됨
    2. get_meeting_summary 또는 get_meeting_context
    3. 질문이 단순함 ("요약", "정리", "알려줘")
    """

    # Tool 1개만 실행?
    if len(tool_results) != 1:
        return False
    
    tool_name = tool_results[0]["tool_name"]
    result = tool_results[0]["result"]

    if "error" in result:
        return False

    # 요약/컨텍스트 Tool?
    if tool_name not in ["get_meeting_summary", "get_meeting_context"]:
        return False
    
    # 질문이 단순함?
    query_lower = query.lower()
    simple_patterns = ["요약", "정리", "알려줘", "보여줘", "뭐였어", "뭐야"]

    if any(p in query_lower for p in simple_patterns):
        return True
    
    return False

    
# -----------------------------------------------------------
# 직접 반환 (LLM 생략)
# -----------------------------------------------------------
def _direct_summary_response(state: dict, tool_results: list) -> dict:
    """
    MongoDB 요약본을 직접 반환 (LLM 생략)
    """
    result = tool_results[0]
    tool_name = result["tool_name"]
    data = result["result"]

    if "error" in data:
        state["answer"] = f"죄송합니다. {data['error']}"
        state["confidence"] = 0.0
        state["sources"] = []
        return state
    
    # get_meeting_summary 직접 포맷팅
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
        
        logger.info("요약본 직접 반환 완료 (LLM 생략)")

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
        
        logger.info("컨텍스트 직접 반환 완료 (LLM 생략)")
    
    return state


# -----------------------------------------------------------
# LLM 기반 답변 (복잡한 질문)
# -----------------------------------------------------------
async def _llm_based_response(state: dict, tool_results: list, query: str, llm) -> dict:
    """
    LLM으로 답변 생성 (복잡한 질문)
    
    사용 시나리오:
    - 다중 Tool 실행
    - search_meeting_transcript (RAG)
    - 복잡한 분석/비교 질문
    """

    # Tool 결과 정리
    tool_context = ""
    sources = []
    
    for result in tool_results:
        tool_name = result["tool_name"]
        data = result["result"]
        
        tool_context += f"\n\n[{tool_name} 결과]:\n"
        
        if "error" in data:
            tool_context += f"오류: {data['error']}\n"
            continue
        
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
        
        elif tool_name == "get_meeting_context":
            tool_context += f"제목: {data.get('title', 'N/A')}\n"
            tool_context += f"요약: {data.get('summary', 'N/A')[:300]}...\n"
            sources.append(data['meeting_id'])
    
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
        state["confidence"] = 0.9 if len(tool_results) >= 2 else 0.7
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
def should_execute_tools(state) -> str:
    """Tool 실행 여부 결정"""
    if state.get("tool_calls"):
        return "execute_tools"
    else:
        return "end"