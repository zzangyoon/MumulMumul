# app/services/feedbackBoard/test.py
import sys
from pathlib import Path

# 이 파일 기준으로 프로젝트 루트 계산
CURRENT_FILE = Path(__file__).resolve()
ROOT_DIR = CURRENT_FILE.parents[3]   # .../MumulMumul
sys.path.append(str(ROOT_DIR))

from datetime import datetime

from app.services.feedbackBoard.nodes.split_intent_node import split_intent_node
from app.services.feedbackBoard.nodes.dedup_within_week_node import dedup_within_week_node, dummy_embed
from app.services.feedbackBoard.schemas import FeedbackBoardPost
from app.services.feedbackBoard.io_contract import FeedbackBoardState, PipelineInput, RunConfig
from app.services.feedbackBoard.nodes.normalize_filter_node import normalize_filter_node


def run_smoke():
    # load_logs_node가 없으니, state.posts를 더미로 직접 채움
    posts = [
        FeedbackBoardPost(
            _id="p1",
            camp_id=1,
            author_id=101,
            raw_text="씨발 팀장이 의견을 안 들어요 그리고 공지 채널도 너무 복잡해요",
            created_at=datetime(2025, 11, 6, 21, 0),
            ai_analysis=None,
        ),
        FeedbackBoardPost(
            _id="p2",
            camp_id=1,
            author_id=102,
            raw_text="ㅋㅋ",
            created_at=datetime(2025, 11, 6, 21, 1),
            ai_analysis=None,
        ),
        FeedbackBoardPost(
            _id="p3",
            camp_id=1,
            author_id=103,
            raw_text="공지 채널이 여러 곳이라 한 번에 보기 어려워요",
            created_at=datetime(2025, 11, 6, 21, 2),
            ai_analysis=None,
        ),
        FeedbackBoardPost(
            _id="p4",
            camp_id=1,
            author_id=103,
            raw_text="공지 사항이 디스코드랑 노션에 흩어져 있어서 확인하기가 너무 불편합니다",
            created_at=datetime(2025, 11, 6, 21, 5),
            ai_analysis=None,
        ),
    ]

    state = FeedbackBoardState(
        input=PipelineInput(config=RunConfig(camp_id=1, week=1, analyzer_version="fb_v1")),
        raw_posts=[],
        posts=posts,
        weekly_context=None,
        weekly_report=None,
        final=None,
        warnings=[],
        errors=[],
    )

    # ---- pipeline----
    state = normalize_filter_node(state)
    state = split_intent_node(state)
    state = dedup_within_week_node(state, dummy_embed)

    # ---- smoke asserts ----
    assert len(state.posts) == 5  # split 반영으로 p1이 2개로 분리됨(분리된 2개 문장)

    # clean_text 채워짐
    assert state.posts[0].ai_analysis.clean_text is not None
    assert state.posts[2].ai_analysis.clean_text is not None

    # meaningless 처리
    assert state.posts[2].ai_analysis.is_active is False
    assert "meaningless" in state.posts[2].ai_analysis.inactive_reasons

    reps = [p for p in state.posts if p.ai_analysis.is_group_representative]
    inactive = [p for p in state.posts if not p.ai_analysis.is_active]

    assert len(reps) == 1
    assert inactive[1].ai_analysis.inactive_reasons == ["near_duplicate"]

    # analyzer_version 찍힘
    assert state.posts[0].ai_analysis.analyzer_version == "fb_v1"

    for p in state.posts:
        print(p.ai_analysis)

    print("✅ smoke_pipeline passed")


if __name__ == "__main__":
    run_smoke()
