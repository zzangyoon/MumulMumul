# app/services/feedbackBoard/nodes/keyword_extract_node.py
from __future__ import annotations

import re
from collections import Counter
from typing import List

from app.services.feedbackBoard.io_contract import FeedbackBoardState


_STOPWORDS = {
    "그냥", "근데", "너무", "진짜", "조금", "같아요", "있어요", "없어요",
    "합니다", "하는", "되어", "해서", "그리고", "그래서", "또", "좀",
    "한", "것", "수", "때", "이번", "주", "주차", "관련",
    "디스코드",  # 필요하면 빼도 됨
}

def _tokenize_ko(text: str) -> List[str]:
    # 아주 단순 토큰화: 한글/숫자/영문만 남기고 분리
    cleaned = re.sub(r"[^0-9A-Za-z가-힣\s]", " ", text)
    tokens = [t.strip() for t in cleaned.split() if t.strip()]
    # 2글자 이상 + 불용어 제외
    tokens = [t for t in tokens if len(t) >= 2 and t not in _STOPWORDS]
    return tokens


def keyword_extract_node(state: FeedbackBoardState, top_k: int = 40) -> FeedbackBoardState:
    """
    active post들의 clean_text 기반으로
    워드클라우드 키워드 후보(top_k)를 뽑아서
    state.weekly_context가 있으면 임시로 state.weekly_context에,
    없으면 state.warnings에만 남겨두는 노드.
    (최종 payload에서는 finalize_node에서 stats/wordcloud_keywords로 실어줄 수 있음)
    """
    active_texts = []
    for p in state.posts:
        if not p.ai_analysis:
            continue
        if not p.ai_analysis.is_active:
            continue
        if p.ai_analysis.clean_text:
            active_texts.append(p.ai_analysis.clean_text)

    if not active_texts:
        state.warnings.append("keyword_extract_node: no active texts")
        # weekly_context 없을 수 있으니 그냥 리턴
        return state

    cnt = Counter()
    for t in active_texts:
        cnt.update(_tokenize_ko(t))

    keywords = [w for w, _ in cnt.most_common(top_k)]

    # weekly_context가 있으면 여기에 넣고, 없으면 finalize에서 별도로 넣을 수 있게 warnings에 남김
    # (WeeklyContext schema에 wordcloud field가 없으면 state.final에서만 쓰도록 운영)
    state.warnings.append(f"keyword_extract_node: extracted_keywords={len(keywords)}")
    # 임시로 state에 저장할 곳이 없으니 state.final이 없을 때 대비하여 errors/warnings에만 남기지 말고
    # state에 직접 들고 다니는 방식이 필요하면 state.weekly_context 만들어질 때 넣으면 됨.
    # 여기서는 간단히 state에 attribute가 없으므로 weekly_context에 임시로 붙이는 편법은 안 씀.

    # 대신: 각 post.ai_analysis.keywords에 top 몇 개를 “개별 글 키워드”로 넣어줄 수도 있음
    # (워드클라우드는 전체 집계지만, 디버그/재현성 측면에서 유용)
    for p in state.posts:
        if p.ai_analysis and p.ai_analysis.is_active and p.ai_analysis.clean_text:
            toks = _tokenize_ko(p.ai_analysis.clean_text)
            p.ai_analysis.keywords = toks[:8]  # 글당 최대 8개 정도

    # 전체 워드클라우드용은 finalize_node에서 재집계하거나,
    # 여기서 state.weekly_context가 생성된 뒤라면 snapshot에 저장하도록 연결해도 됨.
    # 테스트 편의상 state.warnings에 포함시키는 형태로 유지.
    state._tmp_wordcloud_keywords = keywords  # type: ignore[attr-defined]
    return state
