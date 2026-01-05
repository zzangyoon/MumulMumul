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

import re
from typing import List, Sequence, Any, Optional

def pick_representative_idx_rule_based(
    valid_posts: Sequence[Any],   # FeedbackBoardPost list
    dup_group: List[int],         # indices into valid_posts
    *,
    prefer_mid_len: bool = True,
    min_len: int = 20,
    max_len: int = 800,
) -> int:
    """
    dup_group 내 대표 글을 LLM 없이 규칙 기반으로 선택.
    목표:
    - 너무 짧거나(정보 부족), 너무 길거나(군더더기/중복 가능)한 글은 패널티
    - 구두점/문장 경계가 있는 글(설명력이 좋은 글) 가산
    - 마스킹(*) 비율이 과하면 패널티(욕설/공격 표현 비중이 높을 가능성)
    - 숫자/구체 키워드(예: 마감, 일정, 팀장 등)가 약간 있으면 가산(설명 구체성)
    """

    def get_text(idx: int) -> str:
        a = valid_posts[idx].ai_analysis
        return (a.clean_text or "").strip()

    def mask_ratio(text: str) -> float:
        if not text:
            return 1.0
        return text.count("*") / max(1, len(text))

    def sentence_signal(text: str) -> int:
        # 문장부호/줄바꿈이 있으면 설명형일 가능성 가산
        return sum(text.count(x) for x in [".", "?", "!", "\n"])

    def keyword_signal(text: str) -> int:
        # 아주 가벼운 구체성 신호(원하는대로 키워드 튜닝 가능)
        kws = ["마감", "과제", "일정", "팀", "팀장", "공지", "노션", "디스코드", "멘토", "수업", "난이도"]
        return sum(1 for k in kws if k in text)

    def length_score(L: int) -> float:
        # 기본: 길수록 좋은데, 너무 길면 감점
        if L < min_len:
            return -10.0 + (L / max(1, min_len))  # 정보 부족 큰 패널티
        if L > max_len:
            return 5.0 - ((L - max_len) / 200.0)  # 너무 길면 서서히 감점
        # 적정 구간에서는 길이 점수 부여
        return min(8.0, L / 80.0)

    best_idx: Optional[int] = None
    best_score: float = -1e18

    for idx in dup_group:
        text = get_text(idx)
        L = len(text)

        score = 0.0

        # 1) 길이 기반
        score += length_score(L)

        # 2) 문장 신호 가산
        score += 0.7 * sentence_signal(text)

        # 3) 구체 키워드 가산
        score += 0.8 * keyword_signal(text)

        # 4) 마스킹 비율 패널티(높을수록 위험/공격 비중 가능)
        score -= 20.0 * mask_ratio(text)

        # 5) (선택) 너무 길면 '중간 길이'를 선호하도록 살짝 조정
        if prefer_mid_len and (L > 200):
            score -= (L - 200) / 200.0  # 길수록 약간씩 감점

        if score > best_score:
            best_score = score
            best_idx = idx

    # 안전 fallback
    if best_idx is None:
        best_idx = max(dup_group, key=lambda i: len(get_text(i)))

    return best_idx


def dedup_within_week_node(
    state: FeedbackBoardState,
    embed_fn
) -> FeedbackBoardState:
    posts = state.posts
    # 1) (author_id, week) 기준 그룹핑
    group_map = {}

    for p in posts:
        # is_active False인 건 dedup 대상에서 제외
        # clean_text 없는 건 dedup 대상 제외
        if p.ai_analysis is None or not p.ai_analysis.is_active and not p.ai_analysis.clean_text:
            continue

        key = p.author_id
        group_map.setdefault(key, []).append(p)

    for _, group_posts in group_map.items():
        # 2) 그룹 내에서 임베딩 유사도 계산 후 중복군 찾기
        if len(group_posts) <= 1:
            continue
        
        texts = [p.ai_analysis.clean_text for p in group_posts]
        embeddings = np.array(embed_fn(texts))

        sim_matrix = cosine_similarity(embeddings)

        # 3) 유사도 기준으로 중복군 묶기 + 대표 선정 + ai_analysis 필드 업데이트
        visited = set()
        for i, post in enumerate(group_posts):
            if i in visited:
                continue

            dup_group = [i]
            visited.add(i)

            for j in range(i + 1, len(group_posts)):
                if j in visited:
                    continue
                if sim_matrix[i][j] >= state.input.config.dedup_similarity_threshold:
                    dup_group.append(j)
                    visited.add(j)

            if len(dup_group) == 1:
                continue

            # duplicate group id
            group_id = f"dup_{uuid4().hex}"

            # 대표 선정
            rep_idx = pick_representative_idx_rule_based(group_posts, dup_group)


            for idx in dup_group:
                p = group_posts[idx]
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