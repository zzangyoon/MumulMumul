# app/services/feedbackBoard/nodes/normalize_filter_node.py
import sys
from pathlib import Path

# 이 파일 기준으로 프로젝트 루트 계산
CURRENT_FILE = Path(__file__).resolve()
ROOT_DIR = CURRENT_FILE.parents[4]   # .../MumulMumul
sys.path.append(str(ROOT_DIR))

import re
from datetime import datetime
from typing import List, Optional

from app.services.feedbackBoard.schemas import FeedbackBoardPost, FeedbackBoardInsight
from app.services.feedbackBoard.io_contract import FeedbackBoardState


def normalize_filter_node(state: FeedbackBoardState) -> FeedbackBoardState:
    """
    1) raw_text -> clean_text 정제
    2) 의미 없는 글 inactive 처리
    3) 욕설/강한 표현 순화(마스킹)
    """
    if not state.posts:
        state.warnings.append("normalize_filter_node: state.posts is empty")
        return state

    # --- 매우 단순 룰(초기 버전): 추후 운영 정책에 맞게 확장 ---
    meaningless_patterns = [
        r"^\s*$",
        r"^(ㅇ|ㅇㅇ|ㄴㄴ|ㄱㄱ|ㅎㅎ|ㅋㅋ|ㅠㅠ|ㅜㅜ|좋아요|감사|감사합니다|ㄳ|ㄳㄳ)\s*$",
        r"^(test|테스트)\s*$",
        r"^(\.|,|!|\?)+\s*$",
    ]

    # 욕설/강한 표현 마스킹(더미)
    # 운영 시: 욕설 사전/모델로 교체 가능
    profanity_words = [
        "씨발", "시발", "ㅅㅂ", "ㅆㅂ", "병신", "ㅂㅅ", "개새끼", "새끼", "좆", "존나",
    ]

    # 특정 인물 지목 공격(더미 룰): "@홍길동", "OO가", "그 강사" 등은 여기서는 그냥 유지
    # (리스크/토식은 risk_scoring_node에서)

    for p in state.posts:
        if p.ai_analysis is None:
            p.ai_analysis = FeedbackBoardInsight()

        raw = (p.raw_text or "").strip()

        # 1) 기본 정규화
        clean = raw
        clean = clean.replace("\u200b", " ")               # zero-width
        clean = re.sub(r"\s+", " ", clean).strip()        # multi-space -> single

        # 2) 욕설 제거
        for w in profanity_words:
            if w in clean:
                clean = clean.replace(w, "")

        # 3) 의미 없는 글 판단
        inactive_reasons: List[str] = []
        is_meaningless = False
        for pat in meaningless_patterns:
            if re.match(pat, clean, flags=re.IGNORECASE):
                is_meaningless = True
                break

        # 너무 짧은 글(예: 3자 이하)은 의미 없음 처리(초기 룰)
        if len(clean) <= 3:
            is_meaningless = True

        if is_meaningless:
            inactive_reasons.append("meaningless")

        # 4) 적용
        p.ai_analysis.clean_text = clean if clean else None
        p.ai_analysis.analyzed_at = datetime.utcnow()
        p.ai_analysis.analyzer_version = state.input.config.analyzer_version

        if inactive_reasons:
            p.ai_analysis.is_active = False
            # 기존 이유 유지 + 중복 제거
            merged = list(dict.fromkeys((p.ai_analysis.inactive_reasons or []) + inactive_reasons))
            p.ai_analysis.inactive_reasons = merged
        else:
            # 의미 있으면 활성
            p.ai_analysis.is_active = True
            p.ai_analysis.inactive_reasons = p.ai_analysis.inactive_reasons or []

    return state


# -------------------------
# 단독 실행 테스트
# -------------------------
if __name__ == "__main__":
    from app.services.feedbackBoard.io_contract import PipelineInput, RunConfig

    dummy_posts = [
        FeedbackBoardPost(
            id="p1",
            camp_id=1,
            author_id=101,
            raw_text="  씨발  팀장이 의견을 안 들어요...   ",
            created_at=datetime(2025, 11, 6, 21, 0),
            ai_analysis=None,
        ),
        FeedbackBoardPost(
            id="p2",
            camp_id=1,
            author_id=102,
            raw_text="ㅇㅇ",
            created_at=datetime(2025, 11, 6, 21, 5),
            ai_analysis=None,
        ),
        FeedbackBoardPost(
            id="p3",
            camp_id=1,
            author_id=103,
            raw_text="공지 채널이 디스코드/노션으로 나뉘어서 헷갈려요",
            created_at=datetime(2025, 11, 6, 21, 10),
            ai_analysis=None,
        ),
    ]

    state = FeedbackBoardState(
        input=PipelineInput(config=RunConfig(camp_id=1, week=1, analyzer_version="fb_v1")),
        raw_posts=[],
        posts=dummy_posts,
        weekly_context=None,
        weekly_report=None,
        final=None,
        warnings=[],
        errors=[],
    )

    out = normalize_filter_node(state)

    # ---- asserts ----
    assert len(out.posts) == 3
    assert out.posts[0].ai_analysis is not None
    assert out.posts[0].ai_analysis.clean_text is not None
    assert "" in out.posts[0].ai_analysis.clean_text  # 욕설 마스킹 됨

    assert out.posts[1].ai_analysis.is_active is False
    assert "meaningless" in out.posts[1].ai_analysis.inactive_reasons

    assert out.posts[2].ai_analysis.is_active is True
    assert out.posts[2].ai_analysis.clean_text is not None

    for p in out.posts:
        print(p.ai_analysis)
    print("✅ normalize_filter_node standalone test passed")
