# app/services/feedbackBoard/nodes/action_classify_node.py
from __future__ import annotations

from app.services.feedbackBoard.io_contract import FeedbackBoardState


def action_classify_node(state: FeedbackBoardState) -> FeedbackBoardState:
    """
    post.ai_analysis.action_type을 채움.
    - immediate: toxic or high severity, 자해/타해/중도포기 등 강제 high에 준하는 표현, 운영 장애(공지/운영 혼란)도 즉각
    - short: 일정/과제/난이도/마감 등은 단기(조정/가이드/완충)
    - long: 팀문화/관계/번아웃 구조 개선 등은 장기 (단, toxic/high면 immediate가 우선)
    """
    for p in state.posts:
        if not p.ai_analysis:
            continue

        # inactive는 분류 안 함(하지만 원하면 inactive도 찍어둘 수 있음)
        if not p.ai_analysis.is_active:
            continue

        text = (p.ai_analysis.clean_text or p.raw_text or "").strip()

        # 1) 강제 immediate 룰
        if (p.ai_analysis.is_toxic is True) or (p.ai_analysis.severity == "high"):
            p.ai_analysis.action_type = "immediate"
            continue

        # 자해/타해/중도포기/위기 표현
        force_immediate_words = ["죽고싶", "자해", "극단", "그만둘", "포기", "퇴소", "자살", "죽을래"]
        if any(w in text for w in force_immediate_words):
            p.ai_analysis.action_type = "immediate"
            continue

        cat = p.ai_analysis.category or ""
        sub = p.ai_analysis.sub_category or ""

        # 2) 운영/행정은 즉각(공지/채널/규정 등은 빠르게 정리 가능)
        if cat == "운영/행정":
            p.ai_analysis.action_type = "immediate"
            continue

        # 3) 일정/과제/난이도는 단기
        if cat in ("일정 압박", "과제 난이도"):
            p.ai_analysis.action_type = "short"
            continue

        # 4) 번아웃/피로는 장기(단, medium이라도 단기 케어가 필요할 수 있어. 정책 바꾸고 싶으면 여기만 수정)
        if cat == "피로/번아웃":
            p.ai_analysis.action_type = "long"
            continue

        # 5) 팀 갈등은 기본 long (하지만 medium이면 short로 볼 수도 있음 → 운영 정책 선택)
        if cat == "팀 갈등":
            p.ai_analysis.action_type = "long"
            continue

        # default
        p.ai_analysis.action_type = "short"

    return state
