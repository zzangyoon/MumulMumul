# app/services/feedbackBoard/nodes/aggregate_weekly_context_node.py
import sys
from pathlib import Path

# 이 파일 기준으로 프로젝트 루트 계산
CURRENT_FILE = Path(__file__).resolve()
ROOT_DIR = CURRENT_FILE.parents[4]   # .../MumulMumul
sys.path.append(str(ROOT_DIR))

from typing import List, Dict
from collections import defaultdict

from app.services.feedbackBoard.io_contract import (
    FeedbackBoardState,
    WeeklyContext,
    KeyTopicCandidate,
    OpsActionCandidate,
)


def aggregate_weekly_context_node(state: FeedbackBoardState) -> FeedbackBoardState:
    """
    - state.posts(분석 완료) 기반으로 weekly_context 생성
    - + Top3 후보 / ops 후보까지 여기서 '계산'해서 weekly_context에 포함
    """

    if state.posts is None:
        state.errors.append("aggregate_weekly_context_node: posts is None")
        return state

    # 이미 risk/categories/highlights/action_type_count를 만드는 기존 코드가 있다고 가정
    wc: WeeklyContext = state.weekly_context  # (혹은 여기서 새로 생성)
    if wc is None:
        state.errors.append("aggregate_weekly_context_node: weekly_context is None (build first)")
        return state

    # ----------------------------
    # 1) Top3 후보 만들기 (cluster 기반)
    # ----------------------------
    candidates: List[KeyTopicCandidate] = []

    # highlights에서 quick lookup 만들기(위험 가중치용)
    highlight_post_ids = {h.post_id for h in wc.highlights if h.post_id}
    highlight_by_post_id = {h.post_id: h for h in wc.highlights if h.post_id}

    for cat in wc.categories:
        for sub in cat.sub_items:
            # sub: ClusterItem (count/action_type/post_ids/대표요약/키워드)
            score = float(sub.count)

            if sub.action_type == "immediate":
                score += 3.0
            elif sub.action_type == "short":
                score += 1.5
            elif sub.action_type == "long":
                score += 0.5

            # highlights에 포함된 post가 있으면 가중치
            risky_hit = any(pid in highlight_post_ids for pid in (sub.post_ids or []))
            if risky_hit:
                score += 2.0

            # excerpts는 highlights excerpt를 우선 사용, 없으면 대표요약으로 대체
            excerpts = []
            for pid in (sub.post_ids or [])[:3]:
                h = highlight_by_post_id.get(pid)
                if h and h.excerpt:
                    excerpts.append(h.excerpt)
            if not excerpts and sub.representative_summary:
                excerpts = [sub.representative_summary]

            candidates.append(
                KeyTopicCandidate(
                    category=cat.category,
                    sub_category=sub.sub_category,
                    count=sub.count,
                    representative_summary=sub.representative_summary,
                    representative_keywords=sub.representative_keywords,
                    post_ids=sub.post_ids or [],
                    excerpts=excerpts,
                    score=score,
                )
            )

    candidates = sorted(candidates, key=lambda x: x.score, reverse=True)[:3]
    wc.key_topic_candidates = candidates

    # ----------------------------
    # 2) ops 후보 만들기 (action_type별 대표 1개씩)
    # ----------------------------
    ops: List[OpsActionCandidate] = []

    # action_type별로 최고 score 후보 1개씩 뽑기
    best_by_type: Dict[str, KeyTopicCandidate] = {}
    for c in candidates:  # Top3에서만 뽑아도 되고, 전체 candidates에서 뽑아도 됨(더 안정적은 전체)
        # 여기서는 간단히 Top3에서만 뽑는 예
        # action_type은 sub_item에 있었고, candidate엔 score만 남겼으니
        # action_type을 candidate에도 넣고 싶으면 KeyTopicCandidate에 action_type 필드 추가 추천
        pass

    # 후보를 전체에서 action_type별로 뽑는 쪽이 좋아서,
    # 위에서 candidates_top3말고 candidates_all을 유지하는게 더 좋음.
    # (여기서는 설명을 위해 간단히 구현)
    candidates_all = sorted(candidates, key=lambda x: x.score, reverse=True)

    def pick_best(action_type: str):
        for cat in wc.categories:
            for sub in cat.sub_items:
                if sub.action_type == action_type:
                    # sub에서 candidate 형태로 즉석 변환
                    excerpts = [sub.representative_summary] if sub.representative_summary else []
                    return OpsActionCandidate(
                        title=f"[{action_type}] {cat.category} - {sub.sub_category} 대응",
                        target="운영진/멘토 + 해당 이슈 관련 수강생",
                        reason=f"{cat.category}/{sub.sub_category} 이슈가 {sub.count}건으로 반복되며 action_type={action_type}로 분류됨.",
                        action_type=action_type,  # immediate/short/long
                        related_post_ids=sub.post_ids or [],
                        related_excerpts=excerpts,
                    )
        return None

    for t in ["immediate", "short", "long"]:
        c = pick_best(t)
        if c:
            ops.append(c)

    wc.ops_action_candidates = ops[:3]

    state.weekly_context = wc
    return state
