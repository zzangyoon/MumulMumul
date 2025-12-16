# app/services/feedbackBoard/test.py
import sys
from pathlib import Path

CURRENT_FILE = Path(__file__).resolve()
ROOT_DIR = CURRENT_FILE.parents[3]   # .../MumulMumul
sys.path.append(str(ROOT_DIR))

from datetime import datetime

from app.services.feedbackBoard.nodes.normalize_filter_node import normalize_filter_node
from app.services.feedbackBoard.nodes.split_intent_node import split_intent_node
from app.services.feedbackBoard.nodes.dedup_within_week_node import dedup_within_week_node
from app.services.feedbackBoard.nodes.topic_cluster_node import topic_cluster_node

from app.services.feedbackBoard.nodes.keyword_extract_node import keyword_extract_node
from app.services.feedbackBoard.nodes.action_classify_node import action_classify_node
from app.services.feedbackBoard.nodes.aggregate_weekly_context_node import aggregate_weekly_context_node
from app.services.feedbackBoard.nodes.weekly_report_node import weekly_report_node
from app.services.feedbackBoard.nodes.finalize_node import finalize_node

from app.services.feedbackBoard.schemas import FeedbackBoardPost
from app.services.feedbackBoard.io_contract import FeedbackBoardState, PipelineInput, RunConfig

from langchain_openai import ChatOpenAI

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


def run_smoke():
    posts = [
        FeedbackBoardPost(
            post_id="p1",
            camp_id=1,
            author_id=101,
            raw_text="씨발 팀장이 의견을 안 들어요 그리고 공지 채널도 너무 복잡해요",
            created_at=datetime(2025, 11, 6, 21, 0),
            ai_analysis=None,
        ),
        FeedbackBoardPost(
            post_id="p2",
            camp_id=1,
            author_id=102,
            raw_text="ㅋㅋ",
            created_at=datetime(2025, 11, 6, 21, 1),
            ai_analysis=None,
        ),
        FeedbackBoardPost(
            post_id="p3",
            camp_id=1,
            author_id=103,
            raw_text="공지 채널이 여러 곳이라 한 번에 보기 어려워요",
            created_at=datetime(2025, 11, 6, 21, 2),
            ai_analysis=None,
        ),
        FeedbackBoardPost(
            post_id="p4",
            camp_id=1,
            author_id=103,
            raw_text="공지 사항이 디스코드랑 노션에 흩어져 있어서 확인하기가 너무 불편합니다",
            created_at=datetime(2025, 11, 6, 21, 5),
            ai_analysis=None,
        ),
        FeedbackBoardPost(
            post_id="p5",
            camp_id=1,
            author_id=104,
            raw_text="팀장님이 일방적으로 결정하고 의견을 수렴하지 않아요 죽고싶다...ㅜㅜ",
            created_at=datetime(2025, 11, 6, 21, 6),
            ai_analysis=None,
        ),
    ]

    state = FeedbackBoardState(
        input=PipelineInput(
            config=RunConfig(
                camp_id=1,
                week=1,
                category_template=["팀 갈등", "운영/행정", "일정 압박", "과제 난이도", "피로/번아웃"],
                analyzer_version="fb_v1",
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

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.0)

    # ---- pipeline ----
    state = normalize_filter_node(state)
    state = split_intent_node(state)
    state = dedup_within_week_node(state, dummy_embed)
    state = topic_cluster_node(state, dummy_embed)
    # 추가 노드
    state = keyword_extract_node(state, top_k=30)
    state = action_classify_node(state)
    state = aggregate_weekly_context_node(state)
    state = weekly_report_node(state, llm)
    state = finalize_node(state)

    # ---- asserts ----
    assert len(state.errors) == 0, state.errors

    # wordcloud 키워드 생성됨
    assert hasattr(state, "_tmp_wordcloud_keywords")
    assert len(getattr(state, "_tmp_wordcloud_keywords")) > 0

    # action_type이 최소 1개 이상 찍힘
    assert any(
        p.ai_analysis and p.ai_analysis.is_active and p.ai_analysis.action_type in ("immediate", "short", "long")
        for p in state.posts
    )

    # weekly_context 생성
    assert state.weekly_context is not None
    assert state.weekly_context.risk.total >= 1
    assert len(state.weekly_context.categories) >= 1

    # weekly_report 생성
    assert state.weekly_report is not None
    assert isinstance(state.weekly_report.week_summary, str) and len(state.weekly_report.week_summary) > 0
    assert len(state.weekly_report.key_topics) >= 1
    assert len(state.weekly_report.ops_actions) >= 1

    # key_topics에 post_ids가 채워짐
    assert all(len(kt.post_ids) >= 1 for kt in state.weekly_report.key_topics)

    # final payload 생성
    assert state.final is not None
    # assert "risk" in state.final.stats
    # assert len(state.final.logs) >= len(posts)  # split/dedup로 변동 가능하지만 최소 원본 이상인게 일반적

    # ---- debug print ----
    print("=== Weekly Summary ===")
    print(state.final.week_summary)
    print("=== Key Topics ===")
    for kt in state.final.key_topics:
        print("-", kt.category, kt.count, kt.post_ids)
        print("  summary:", kt.summary)

    print("=== Ops Actions ===")
    for a in state.final.ops_actions:
        print("-", a.action_type, a.title)

    print("=== Wordcloud Keywords (top10) ===")
    print(state.final.wordcloud_keywords[:10])

    print("✅ smoke_pipeline extended (.. -> keyword -> action -> aggregate -> weekly_report -> finalize) passed")


if __name__ == "__main__":
    run_smoke()
