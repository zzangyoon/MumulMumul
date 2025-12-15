# app/services/feedbackBoard/nodes/split_intent_node.py
import sys
from pathlib import Path

# 이 파일 기준으로 프로젝트 루트 계산
CURRENT_FILE = Path(__file__).resolve()
ROOT_DIR = CURRENT_FILE.parents[4]   # .../MumulMumul
sys.path.append(str(ROOT_DIR))

import re
from typing import List
from copy import deepcopy

from app.services.feedbackBoard.schemas import FeedbackBoardPost, FeedbackBoardInsight
from app.services.feedbackBoard.io_contract import FeedbackBoardState


def split_intent_node(state: FeedbackBoardState) -> FeedbackBoardState:
    """
    하나의 글에 서로 다른 의미 축(카테고리 가능성)이 있을 경우 split
    - rule-based 1차 버전 (LLM 이전 단계)
    """
    if not state.posts:
        state.warnings.append("split_intent_node: state.posts is empty")
        return state

    new_posts: List[FeedbackBoardPost] = []

    # 아주 보수적인 split 기준 (초기)
    # → 나중에 LLM으로 교체 예정
    split_patterns = [
        r"(?:그리고|근데|하지만|또한|한편)\s*",  # 비캡처 + 뒤 공백까지 같이 제거
        r"(?:\n|[.?!])\s*",                      # 문장부호 기준도 비캡처로
    ]

    for post in state.posts:
        analysis = post.ai_analysis
        if analysis is None or not analysis.is_active:
            new_posts.append(post)
            continue

        clean_text = analysis.clean_text
        if not clean_text:
            new_posts.append(post)
            continue

        # split 후보 문장 생성
        segments = [clean_text]
        for pat in split_patterns:
            tmp = []
            for seg in segments:
                tmp.extend([s.strip() for s in re.split(pat, seg) if s.strip()])
            segments = tmp

        # 너무 많이 쪼개지면 원문 유지
        if len(segments) <= 1:
            new_posts.append(post)
            continue

        # 실제 split 개수 제한
        segments = segments[: state.input.config.split_max_parts]

        # 원본 post → parent로 유지
        # parent_post = post
        # parent_post.ai_analysis.is_active = False  # parent는 비활성화
        # new_posts.append(parent_post)

        # child post 생성
        for idx, seg in enumerate(segments):
            if seg == clean_text:
                continue

            child = FeedbackBoardPost(
                id=f"{post.id}_split_{idx}",
                camp_id=post.camp_id,
                author_id=post.author_id,
                raw_text=seg,
                created_at=post.created_at,
                ai_analysis=FeedbackBoardInsight(
                    clean_text=seg,
                    parent_post_id=post.id,
                    is_split_child=True,
                    split_index=idx,
                    is_active=True,
                    analyzer_version=analysis.analyzer_version,
                ),
            )
            new_posts.append(child)

    state.posts = new_posts
    return state

if __name__ == "__main__":
    from datetime import datetime
    from app.services.feedbackBoard.io_contract import PipelineInput, RunConfig

    post = FeedbackBoardPost(
        id="p1",
        camp_id=1,
        author_id=101,
        raw_text="팀장이 의견을 안 들어요. 그리고 공지 채널도 너무 복잡해요.",
        created_at=datetime.utcnow(),
        ai_analysis=FeedbackBoardInsight(
            clean_text="팀장이 의견을 안 들어요. 그리고 공지 채널도 너무 복잡해요.",
            is_active=True,
            analyzer_version="fb_v1",
        ),
    )

    state = FeedbackBoardState(
        input=PipelineInput(config=RunConfig(camp_id=1, week=1)),
        raw_posts=[],
        posts=[post],
        weekly_context=None,
        weekly_report=None,
        final=None,
        warnings=[],
        errors=[],
    )

    out = split_intent_node(state)

    # ---- asserts ----
    assert len(out.posts) >= 2
    parents = [p for p in out.posts if p.id == "p1"]
    children = [p for p in out.posts if p.id.startswith("p1_split")]

    assert len(parents) == 1
    assert len(children) >= 1
    assert children[0].ai_analysis.is_split_child is True
    assert children[0].ai_analysis.parent_post_id == "p1"

    print("✅ split_intent_node standalone test passed")
