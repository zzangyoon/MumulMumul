# app/services/feedbackBoard/graph.py
from __future__ import annotations

from typing import Callable, List, Optional

from langgraph.graph import StateGraph, END

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
import numpy as np

from app.services.feedbackBoard.schemas import FeedbackBoardPost
from app.services.feedbackBoard.io_contract import FeedbackBoardState, FinalizePayload, PipelineInput, RunConfig

from app.services.feedbackBoard.nodes.normalize_filter_node import normalize_filter_node
from app.services.feedbackBoard.nodes.split_intent_node import split_intent_node
from app.services.feedbackBoard.nodes.dedup_within_week_node import dedup_within_week_node
from app.services.feedbackBoard.nodes.topic_cluster_node import topic_cluster_node
from app.services.feedbackBoard.nodes.keyword_extract_node import keyword_extract_node
from app.services.feedbackBoard.nodes.action_classify_node import action_classify_node
from app.services.feedbackBoard.nodes.aggregate_weekly_context_node import aggregate_weekly_context_node
from app.services.feedbackBoard.nodes.weekly_report_node import weekly_report_node
from app.services.feedbackBoard.nodes.finalize_node import finalize_node


EmbedFn = Callable[[List[str]], List[List[float]]]
OpenAIEmbedFn = OpenAIEmbeddings.embed_documents

def dummy_embed(texts):
    """
    테스트용 임베딩:
    - 공지/운영 계열 => [0, 1]
    - 팀/팀장 계열 => [1, 0]
    - 그 외 => [0.5, 0.5]
    """
    out = []
    for t in texts:
        if ("공지" in t) or ("운영" in t) or ("노션" in t) or ("디스코드" in t):
            out.append([0.0, 1.0])
        elif ("팀장" in t) or ("팀 " in t) or ("팀" in t):
            out.append([1.0, 0.0])
        else:
            out.append([0.5, 0.5])
    return out

def build_feedbackboard_graph(
    llm: ChatOpenAI,
    *,
    top_k_keywords: int = 30,
):
    """
    normalize -> split -> dedup -> cluster -> keyword -> action -> aggregate -> weekly_report -> finalize
    를 LangGraph로 묶은 Graph(CompiledGraph)를 반환한다.
    """

    graph = StateGraph(FeedbackBoardState)

    # -----------------------------
    # wrappers (노드 시그니처 통일)
    # -----------------------------
    def _normalize(state: FeedbackBoardState) -> FeedbackBoardState:
        return normalize_filter_node(state)

    def _split(state: FeedbackBoardState) -> FeedbackBoardState:
        return split_intent_node(state)

    def _dedup(state: FeedbackBoardState) -> FeedbackBoardState:
        return dedup_within_week_node(state, dummy_embed)

    def _cluster(state: FeedbackBoardState) -> FeedbackBoardState:
        return topic_cluster_node(state, dummy_embed)

    def _keyword(state: FeedbackBoardState) -> FeedbackBoardState:
        return keyword_extract_node(state, top_k=top_k_keywords)

    def _action(state: FeedbackBoardState) -> FeedbackBoardState:
        return action_classify_node(state)

    def _aggregate(state: FeedbackBoardState) -> FeedbackBoardState:
        return aggregate_weekly_context_node(state)

    def _weekly_report(state: FeedbackBoardState) -> FeedbackBoardState:
        return weekly_report_node(state, llm)

    def _finalize(state: FeedbackBoardState) -> FeedbackBoardState:
        return finalize_node(state)

    # -----------------------------
    # add nodes
    # -----------------------------
    graph.add_node("normalize", _normalize)
    graph.add_node("split", _split)
    graph.add_node("dedup", _dedup)
    graph.add_node("cluster", _cluster)
    graph.add_node("keyword", _keyword)
    graph.add_node("action", _action)
    graph.add_node("aggregate", _aggregate)
    graph.add_node("weekly_report", _weekly_report)
    graph.add_node("finalize", _finalize)

    # -----------------------------
    # edges
    # -----------------------------
    graph.set_entry_point("normalize")
    graph.add_edge("normalize", "split")
    graph.add_edge("split", "dedup")
    graph.add_edge("dedup", "cluster")
    graph.add_edge("cluster", "keyword")
    graph.add_edge("keyword", "action")
    graph.add_edge("action", "aggregate")
    graph.add_edge("aggregate", "weekly_report")
    graph.add_edge("weekly_report", "finalize")
    graph.add_edge("finalize", END)

    return graph.compile()


def run_feedbackboard_pipeline(
    posts: List[FeedbackBoardPost],
    *,
    camp_id: int,
    week: int,
    category_template: List[str],
    analyzer_version: str = "fb_v1",
    llm: Optional[ChatOpenAI] = None,
    top_k_keywords: int = 30,
) -> FinalizePayload:
    """
    - posts + config로 FeedbackBoardState 생성
    - LangGraph 실행
    - 최종 state.final(FinalizePayload)을 리턴
    """

    if llm is None:
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.0)

    state = FeedbackBoardState(
        input=PipelineInput(
            config=RunConfig(
                camp_id=camp_id,
                week=week,
                category_template=category_template,
                analyzer_version=analyzer_version,
            )
        ),
        raw_posts=[],
        posts=posts,
        weekly_context=None,
        weekly_report=None,
        final=None,
        warnings=[],
        errors=[],
    )

    app = build_feedbackboard_graph(llm=llm, top_k_keywords=top_k_keywords)
    out_state: FeedbackBoardState = app.invoke(state)

    print(out_state)

    # 에러가 누적되면 여기서 예외로 터뜨리거나, 그냥 리턴 정책을 선택 가능
    if len(out_state['errors']) > 0:
        print("FeedbackBoard pipeline errors:", out_state['errors'])
        # 필요하면 raise 대신 return out_state 로 바꿔도 됨
        raise RuntimeError(f"feedbackBoard pipeline failed: {out_state.errors}")

    return out_state['final']
