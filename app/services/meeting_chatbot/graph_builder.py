from langgraph.graph import StateGraph, END
from .state import ChatbotState
from .nodes import (
    agent_decide,
    execute_tools,
    generate_final_answer,
    should_execute_tools
)
from .tools import MEETING_TOOLS

def build_graph(llm, vector_store=None, mongo_service=None):
    """
    Tool 기반 Agent Graph 구성
    
    플로우:
    1. agent_decide: LLM이 Tool 선택
    2. execute_tools: 선택된 Tool 실행
    3. generate_final_answer: 최종 답변 생성
    """

    # LLM에 Tool 바인딩
    llm_with_tools = llm.bind_tools(MEETING_TOOLS)

    graph = StateGraph(ChatbotState)

    # 노드 추가
    async def decide_wrapper(st):
        return await agent_decide(st, llm_with_tools)

    async def execute_wrapper(st):
        return await execute_tools(st)

    async def answer_wrapper(st):
        return await generate_final_answer(st, llm)
    
    graph.add_node("agent_decide", decide_wrapper)
    graph.add_node("execute_tools", execute_wrapper)
    graph.add_node("generate_final_answer", answer_wrapper)

    # 엣지 구성
    graph.set_entry_point("agent_decide")

    # 조건부 분기
    graph.add_conditional_edges(
        "agent_decide",
        should_execute_tools,
        {
            "execute_tools" : "execute_tools",
            "end" : END
        }
    )

    # Tool 실행 -> 답변 생성
    graph.add_edge("execute_tools", "generate_final_answer")
    graph.add_edge("generate_final_answer", END)

    return graph.compile()
