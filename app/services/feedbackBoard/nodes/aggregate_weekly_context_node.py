# app/services/feedbackBoard/nodes/aggregate_weekly_context_node.py
from __future__ import annotations

from typing import List, Dict, Optional
from collections import defaultdict, Counter

from app.services.feedbackBoard.io_contract import (
    FeedbackBoardState,
    WeeklyContext,
    RiskAgg,
    CategoryAgg,
    ClusterItem,
    RiskHighlight,
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

    cfg = state.input.config
    posts = state.posts

    # ----------------------------
    # 0) active post만 집계 대상으로
    # ----------------------------
    active_posts = [
        p for p in posts
        if p.ai_analysis and p.ai_analysis.is_active and (p.ai_analysis.clean_text is not None)
    ]

    # ----------------------------
    # 1) RiskAgg 계산
    # ----------------------------
    sev_cnt = Counter()
    toxic_cnt = 0

    for p in active_posts:
        sev = p.ai_analysis.severity or "low"
        sev_cnt[sev] += 1
        if p.ai_analysis.is_toxic:
            toxic_cnt += 1

    danger_count = sum(
        1 for p in active_posts
        if (p.ai_analysis.is_toxic is True) or (p.ai_analysis.severity == "high")
    )
    warning_count = sum(
        1 for p in active_posts
        if (p.ai_analysis.severity == "medium") and (p.ai_analysis.is_toxic is not True)
    )
    normal_count = max(0, len(active_posts) - danger_count - warning_count)

    risk = RiskAgg(
        total=len(active_posts),
        toxic_count=int(toxic_cnt),
        severity_count={
            "low": int(sev_cnt.get("low", 0)),
            "medium": int(sev_cnt.get("medium", 0)),
            "high": int(sev_cnt.get("high", 0)),
        },
        danger_count=int(danger_count),
        warning_count=int(warning_count),
        normal_count=int(normal_count),
    )

    # ----------------------------
    # 2) RiskHighlight (TopK)
    # ----------------------------
    def _risk_rank(p):
        sev = p.ai_analysis.severity or "low"
        sev_r = 0 if sev == "high" else 1 if sev == "medium" else 2
        tox_r = 0 if p.ai_analysis.is_toxic else 1
        # 최신이 앞으로
        return (sev_r, tox_r, -p.created_at.timestamp())

    highlight_src = [
        p for p in active_posts
        if (p.ai_analysis.is_toxic is True) or (p.ai_analysis.severity in ("high", "medium"))
    ]
    highlight_src = sorted(highlight_src, key=_risk_rank)[:6]

    highlights: List[RiskHighlight] = []
    for i, p in enumerate(highlight_src):
        excerpt = (p.ai_analysis.clean_text or p.raw_text or "")[:120]
        highlights.append(
            RiskHighlight(
                post_id=p.post_id,
                created_at=p.created_at,
                author_id=p.author_id,
                category=p.ai_analysis.category,
                sub_category=p.ai_analysis.sub_category,
                severity=p.ai_analysis.severity,
                is_toxic=p.ai_analysis.is_toxic,
                summary=p.ai_analysis.summary,
                excerpt=excerpt,
            )
        )

    # highlights quick lookup (가중치/발췌 우선 사용용)
    highlight_post_ids = {h.post_id for h in highlights if h.post_id}
    highlight_by_post_id = {h.post_id: h for h in highlights if h.post_id}

    # ----------------------------
    # 3) categories / sub_items(ClusterItem) 집계
    # ----------------------------
    bucket: Dict[str, Dict[str, List]] = defaultdict(lambda: defaultdict(list))
    for p in active_posts:
        cat = p.ai_analysis.category or "기타"
        sub = p.ai_analysis.sub_category or "기타"
        bucket[cat][sub].append(p)

    categories: List[CategoryAgg] = []
    action_type_cnt = Counter()
    local_cluster_id = 0

    # action_type 우선순위: immediate > short > long
    def _rank_action(a: Optional[str]) -> int:
        if a == "immediate":
            return 0
        if a == "short":
            return 1
        if a == "long":
            return 2
        return 3

    for cat, sub_map in bucket.items():
        cat_count = sum(len(v) for v in sub_map.values())
        sub_items: List[ClusterItem] = []

        for sub, plist in sub_map.items():
            local_cluster_id += 1

            # 대표 선정: (severity 우선) + (길이 우선)
            plist_sorted = sorted(
                plist,
                key=lambda p: (
                    0 if (p.ai_analysis.severity == "high") else
                    1 if (p.ai_analysis.severity == "medium") else 2,
                    -len(p.ai_analysis.clean_text or p.raw_text or ""),
                ),
            )
            rep = plist_sorted[0]

            rep_sum = rep.ai_analysis.summary or (rep.ai_analysis.clean_text or rep.raw_text or "")[:80]
            rep_kw = list(rep.ai_analysis.keywords or [])[:8]

            # 서브 그룹 action_type: 가장 급한 것(최소 rank)
            at_list = [p.ai_analysis.action_type for p in plist if p.ai_analysis.action_type]
            action_type = None
            if at_list:
                action_type = sorted(at_list, key=_rank_action)[0]
                action_type_cnt[action_type] += len(plist)

            sub_items.append(
                ClusterItem(
                    local_cluster_id=local_cluster_id,
                    sub_category=sub,
                    representative_summary=rep_sum,
                    representative_keywords=rep_kw,
                    count=len(plist),
                    action_type=action_type,
                    post_ids=[p.post_id for p in plist],
                )
            )

        categories.append(
            CategoryAgg(
                category=cat,
                count=cat_count,
                sub_items=sub_items,
            )
        )

    # ----------------------------
    # 4) WeeklyContext 생성 (여기까지가 "weekly_context 계산")
    # ----------------------------
    wc = WeeklyContext(
        camp_id=cfg.camp_id,
        week=cfg.week,
        range=cfg.range,
        risk=risk,
        categories=categories,
        highlights=highlights,
        action_type_count={
            "immediate": int(action_type_cnt.get("immediate", 0)),
            "short": int(action_type_cnt.get("short", 0)),
            "long": int(action_type_cnt.get("long", 0)),
        },
    )

    # ----------------------------
    # 5) Top3 후보 만들기 (cluster 기반)
    # ----------------------------
    candidates_all: List[KeyTopicCandidate] = []

    for cat in wc.categories:
        for sub in cat.sub_items:
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

            # excerpts: highlights excerpt 우선, 없으면 대표요약 1개
            excerpts: List[str] = []
            for pid in (sub.post_ids or [])[:3]:
                h = highlight_by_post_id.get(pid)
                if h and h.excerpt:
                    excerpts.append(h.excerpt)
            if not excerpts and sub.representative_summary:
                excerpts = [sub.representative_summary]

            candidates_all.append(
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

    wc.key_topic_candidates = sorted(candidates_all, key=lambda x: x.score, reverse=True)[:3]

    # ----------------------------
    # 6) ops 후보 만들기 (action_type별 대표 1개씩)
    #    - Top3에서만 뽑지 않고, candidates_all 전체에서 뽑는 게 더 안정적
    # ----------------------------
    ops: List[OpsActionCandidate] = []

    def pick_best_ops(action_type: str) -> Optional[OpsActionCandidate]:
        best = None
        best_score = -1.0

        for cat in wc.categories:
            for sub in cat.sub_items:
                if sub.action_type != action_type:
                    continue

                # sub 단위 점수(Top3 후보와 동일 규칙)
                s = float(sub.count)
                if action_type == "immediate":
                    s += 3.0
                elif action_type == "short":
                    s += 1.5
                elif action_type == "long":
                    s += 0.5

                risky_hit = any(pid in highlight_post_ids for pid in (sub.post_ids or []))
                if risky_hit:
                    s += 2.0

                if s > best_score:
                    best_score = s
                    best = OpsActionCandidate(
                        title=f"[{action_type}] {cat.category} - {sub.sub_category} 대응",
                        target="운영진/멘토 + 해당 이슈 관련 수강생",
                        reason=(
                            f"{cat.category}/{sub.sub_category} 이슈가 {sub.count}건으로 반복되며 "
                            f"action_type={action_type}로 분류됨."
                        ),
                        action_type=action_type,
                        related_post_ids=sub.post_ids or [],
                        related_excerpts=[sub.representative_summary] if sub.representative_summary else [],
                    )
        return best

    for t in ["immediate", "short", "long"]:
        c = pick_best_ops(t)
        if c:
            ops.append(c)

    wc.ops_action_candidates = ops[:3]

    state.weekly_context = wc
    return state
