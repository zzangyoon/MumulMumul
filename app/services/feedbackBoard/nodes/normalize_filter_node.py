from __future__ import annotations

from datetime import datetime
import re

from app.services.feedbackBoard.io_contract import FeedbackBoardState
from app.services.feedbackBoard.schemas import FeedbackBoardInsight


def normalize_filter_node(state: FeedbackBoardState) -> FeedbackBoardState:
    cfg = state.input.config

    # ---- 룰 세트 (추후 cfg로 뺄 수 있지만 지금은 노드 안에 둠) ----
    # 욕설/공격 표현(토식 판정용)
    TOXIC_WORDS = [
        "씨발", "시발", "좆", "병신", "미친", "개새", "꺼져", "죽어", "븅", "ㅅㅂ",
    ]

    # “강제 high” 신호 (운영진이 반드시 봐야 하는 것들)
    FORCE_HIGH_PATTERNS = [
        r"자해", r"죽고\s*싶", r"죽어\s*버리", r"극단적\s*선택",
        r"폭행", r"살해", r"죽이", r"협박",
        r"중도\s*포기", r"그만\s*둘", r"퇴소", r"환불",
    ]

    # 의미 없는 글(최소 룰)
    MEANINGLESS_PATTERNS = [
        r"^[ㅋㅎㅠㅜ]+$",          # ㅋㅋㅋ / ㅠㅠㅠ 등
        r"^\s*$",                  # 공백
        r"^ㅇㅋ$|^ㅇㅇ$|^ㄱㅅ$",     # 매우 짧은 반응
    ]

    def _is_meaningless(text: str) -> bool:
        t = (text or "").strip()
        if len(t) <= 1:
            return True
        for pat in MEANINGLESS_PATTERNS:
            if re.match(pat, t):
                return True
        return False

    def _clean_text(text: str) -> str:
        t = (text or "").strip()
        # 기본 정리
        t = re.sub(r"\s+", " ", t)
        # 욕설 마스킹
        for w in TOXIC_WORDS:
            t = t.replace(w, "*" * len(w))
        return t

    def _toxicity_score(raw: str) -> float:
        raw = raw or ""
        hits = sum(1 for w in TOXIC_WORDS if w in raw)
        # 간단 스케일링: 0, 0.33, 0.66, 1.0
        return min(1.0, hits / 3.0)

    def _has_force_high(raw: str) -> bool:
        raw = raw or ""
        for pat in FORCE_HIGH_PATTERNS:
            if re.search(pat, raw):
                return True
        return False

    # ---- main ----
    new_posts = []
    for p in state.posts:
        if p.ai_analysis is None:
            p.ai_analysis = FeedbackBoardInsight()

        raw = p.raw_text or ""

        # (1) clean_text
        p.ai_analysis.clean_text = _clean_text(raw)

        # (2) meaningless → inactive
        if _is_meaningless(p.ai_analysis.clean_text):
            p.ai_analysis.is_active = False
            if "meaningless" not in p.ai_analysis.inactive_reasons:
                p.ai_analysis.inactive_reasons.append("meaningless")
        else:
            p.ai_analysis.is_active = True

        # (3) risk scoring 동시 수행 (원문 raw 기준)
        # - split 이후 clean_text에서 욕설이 사라져도 “원문에 있었던 위험 신호”는 남김
        score = _toxicity_score(raw)
        p.ai_analysis.toxicity_score = score
        p.ai_analysis.is_toxic = score > 0.0

        # severity: 강제 high > toxic high > 기본 low
        # (필요하면 "중도포기/환불" 같은 것만 medium으로 내리는 룰로 세분화 가능)
        if _has_force_high(raw):
            p.ai_analysis.severity = "high"
        elif p.ai_analysis.is_toxic:
            p.ai_analysis.severity = "high"
        else:
            # 의미 있는 글이면 medium/low를 좀 더 구분할 수도 있지만,
            # 지금은 간단히 low로 둠 (이후 risk 정책 확장 가능)
            p.ai_analysis.severity = "low"

        # (4) meta
        p.ai_analysis.analyzed_at = datetime.utcnow()
        p.ai_analysis.analyzer_version = cfg.analyzer_version

        new_posts.append(p)

    state.posts = new_posts
    return state
