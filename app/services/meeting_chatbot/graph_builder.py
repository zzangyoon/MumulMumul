from langgraph.graph import StateGraph, END
from .state import ChatbotState
from .nodes import (
    agent_decide,
    execute_actions,
    generate_final_answer,
    should_execute_actions
)

def build_graph(llm):
    """
    Tool-Orchestrated Agent Graph 구성
    
    플로우:
    1. agent_decide: Decision Making (Intent 결정)
    2. execute_actions: Action Excution (Tool 실행)
    3. generate_final_answer: 최종 답변 생성

    Decision -> Action -> Observation -> Answer
    """

    graph = StateGraph(ChatbotState)

    # 노드 추가
    async def decide_wrapper(st):
        return await agent_decide(st, llm)

    async def execute_wrapper(st):
        return await execute_actions(st)

    async def answer_wrapper(st):
        return await generate_final_answer(st, llm)
    
    graph.add_node("agent_decide", decide_wrapper)
    graph.add_node("execute_actions", execute_wrapper)
    graph.add_node("generate_final_answer", answer_wrapper)

    # 엣지 구성
    graph.set_entry_point("agent_decide")

    # 조건부 분기: Decision -> Action 또는 종료
    graph.add_conditional_edges(
        "agent_decide",
        should_execute_actions,
        {
            "execute_actions" : "execute_actions",
            "end" : END
        }
    )

    # Action -> 답변 생성
    graph.add_edge("execute_actions", "generate_final_answer")
    graph.add_edge("generate_final_answer", END)

    return graph.compile()
