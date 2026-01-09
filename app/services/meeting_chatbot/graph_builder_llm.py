"""
LLM 기반 Agent Graph Builder

기존 graph_builder.py(규칙 기반)와 별도로 운영
"""

from langgraph.graph import StateGraph, END
from .state import ChatbotState
from .nodes_llm import (
    agent_decide_llm,
    execute_actions_llm,
    generate_final_answer_llm,
    should_execute_actions_llm
)


def build_graph_llm(llm):
    """
    LLM 기반 Agent Graph 구성
    
    플로우:
    1. agent_decide_llm: LLM이 Intent + Entity 결정
    2. execute_actions_llm: Tool 실행
    3. generate_final_answer_llm: LLM이 최종 답변 생성
    """

    graph = StateGraph(ChatbotState)

    # 노드 래퍼
    async def decide_wrapper(st):
        return await agent_decide_llm(st, llm)

    async def execute_wrapper(st):
        return await execute_actions_llm(st)

    async def answer_wrapper(st):
        return await generate_final_answer_llm(st, llm)

    # 노드 추가
    graph.add_node("agent_decide", decide_wrapper)
    graph.add_node("execute_actions", execute_wrapper)
    graph.add_node("generate_final_answer", answer_wrapper)

    # 엣지 구성
    graph.set_entry_point("agent_decide")

    graph.add_conditional_edges(
        "agent_decide",
        should_execute_actions_llm,
        {
            "execute_actions": "execute_actions",
            "end": END
        }
    )

    graph.add_edge("execute_actions", "generate_final_answer")
    graph.add_edge("generate_final_answer", END)

    return graph.compile()
