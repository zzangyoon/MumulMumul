# app/services/feedbackBoard/nodes/dedup_within_week_node.py
import sys
from pathlib import Path

# 이 파일 기준으로 프로젝트 루트 계산
CURRENT_FILE = Path(__file__).resolve()
ROOT_DIR = CURRENT_FILE.parents[4]   # .../MumulMumul
sys.path.append(str(ROOT_DIR))

from typing import List
from uuid import uuid4

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

from app.services.feedbackBoard.schemas import FeedbackBoardPost
from app.services.feedbackBoard.io_contract import FeedbackBoardState

def dummy_embed(texts):
    # 같은 의미면 거의 같은 벡터 나오게
    return [
        np.array([1.0, 0.0]) if "공지" in t else np.array([0.0, 1.0])
        for t in texts
    ]


def dedup_within_week_node(
    state: FeedbackBoardState,
    embed_fn,  # embedding 함수 주입 (ex. OpenAIEmbeddings().embed_documents)
) -> FeedbackBoardState:
    posts = state.posts
    # 1) (author_id, week) 기준 그룹핑
    group_map = {}

    for p in posts:
        # is_active False인 건 dedup 대상에서 제외
        if p.ai_analysis is None or not p.ai_analysis.is_active:
            continue

        key = (p.author_id, p.created_at.isocalendar().week)
        group_map.setdefault(key, []).append(p)

    for _, group_posts in group_map.items():
        if len(group_posts) <= 1:
            continue
        
        # clean_text 없는 건 dedup 대상 제외
        valid_posts = [
            p for p in group_posts
            if p.ai_analysis and p.ai_analysis.clean_text and p.ai_analysis.is_active
        ]
        if len(valid_posts) <= 1:
            continue
        
        texts = [p.ai_analysis.clean_text for p in valid_posts]
        embeddings = np.array(embed_fn(texts))

        sim_matrix = cosine_similarity(embeddings)

        visited = set()
        for i, base_post in enumerate(valid_posts):
            if i in visited:
                continue

            dup_group = [i]
            visited.add(i)

            for j in range(i + 1, len(valid_posts)):
                if j in visited:
                    continue
                if sim_matrix[i][j] >= state.input.config.dedup_similarity_threshold:
                    dup_group.append(j)
                    visited.add(j)

            if len(dup_group) == 1:
                continue

            # duplicate group id
            group_id = f"dup_{uuid4().hex}"

            # 대표 선정: clean_text 길이가 가장 긴 것
            rep_idx = max(
                dup_group,
                key=lambda idx: len(valid_posts[idx].ai_analysis.clean_text)
            )

            for idx in dup_group:
                p = valid_posts[idx]
                p.ai_analysis.duplicate_group_id = group_id

                if idx == rep_idx:
                    p.ai_analysis.is_group_representative = True
                else:
                    p.ai_analysis.is_group_representative = False
                    p.ai_analysis.is_active = False
                    p.ai_analysis.inactive_reasons.append("near_duplicate")
    
    state.posts = posts
    return state

if __name__ == "__main__":
    from datetime import datetime
    from app.services.feedbackBoard.schemas import FeedbackBoardPost, FeedbackBoardInsight
    from app.services.feedbackBoard.io_contract import FeedbackBoardState, PipelineInput, RunConfig
    from app.services.feedbackBoard.nodes.dedup_within_week_node import dedup_within_week_node

    posts = [
        FeedbackBoardPost(
            _id="p3",
            camp_id=1,
            author_id=103,
            raw_text="공지 채널이 여러 곳이라 한 번에 보기 어려워요",
            created_at=datetime(2025, 11, 6, 21, 2),
            ai_analysis=FeedbackBoardInsight(
                clean_text="공지 채널이 여러 곳이라 한 번에 보기 어려워요"
            ),
        ),
        FeedbackBoardPost(
            _id="p4",
            camp_id=1,
            author_id=103,
            raw_text="공지사항이 디스코드랑 노션에 흩어져 있어서 확인하기가 불편합니다",
            created_at=datetime(2025, 11, 6, 21, 5),
            ai_analysis=FeedbackBoardInsight(
                clean_text="공지사항이 여러 곳에 흩어져 있어 확인하기가 불편합니다"
            ),
        ),
    ]

    state = FeedbackBoardState(
        input=PipelineInput(
            config=RunConfig(camp_id=1, dedup_similarity_threshold=0.8)
        ),
        posts=posts,
    )

    out = dedup_within_week_node(state, dummy_embed)

    reps = [p for p in out.posts if p.ai_analysis.is_group_representative]
    inactive = [p for p in out.posts if not p.ai_analysis.is_active]

    for p in out.posts:
        print(p.ai_analysis)

    assert len(reps) == 1
    assert len(inactive) == 1
    assert inactive[0].ai_analysis.inactive_reasons == ["near_duplicate"]