# app/services/feedbackBoard/nodes/keyword_extract_node.py
from __future__ import annotations

from functools import cache
import re
from collections import Counter
from typing import List, Optional

from app.services.feedbackBoard.io_contract import FeedbackBoardState


_STOPWORDS = {
    "그냥", "근데", "너무", "진짜", "조금", "같아요", "있어요", "없어요",
    "합니다", "하는", "되어", "해서", "그리고", "그래서", "또", "좀",
    "한", "것", "수", "때", "이번", "주", "주차", "관련", "좋겠어요",
}

# Kiwi는 무겁지 않지만 매 호출마다 만들면 느려서, 모듈 레벨에서 1번만 생성 권장
_KIWI = None

@cache
def _get_kiwi():
    global _KIWI
    if _KIWI is None:
        from kiwipiepy import Kiwi
        _KIWI = Kiwi()
    return _KIWI

def _normalize_token_form(token_form: str) -> str:
    """
    최소 정제:
    - 공백/특수문자 제거
    - 너무 짧은 토큰 제거는 바깥에서 처리
    """
    t = re.sub(r"[^0-9A-Za-z가-힣]", "", token_form)
    return t.strip()


def _tokenize_ko_kiwi(
    text: str,
    *,
    min_len: int = 2,
    allowed_pos: Optional[set[str]] = None,
) -> List[str]:
    """
    Kiwi 기반 토크나이징:
    - 품사 필터링 (기본: 명사/동사/형용사/영문/숫자)
    - 동사/형용사는 원형(lemma) + '다' 형태로 통일
    - 불용어 제거
    """
    kiwi = _get_kiwi()

    if allowed_pos is None:
        # Kiwi POS 예시:
        # NNG/NNP/NNB/NR/NP: 명사류
        # VV: 동사, VA: 형용사
        # SL: 외국어(영문), SN: 숫자
        allowed_pos = {"NNG", "NNP", "NNB", "NR", "NP", "VV", "VA", "SL", "SN"}

    text = (text or "").strip()
    if not text:
        return []

    result = kiwi.analyze(text, top_n=1)
    if not result:
        return []

    tokens = []
    # result[0][0] = 형태소 리스트
    morphs = result[0][0]

    for m in morphs:
        form = m.form
        tag = m.tag

        if tag not in allowed_pos:
            continue

        # 원형/활용 정규화
        # - 동사(VV), 형용사(VA)는 기본형 + "다"로 통일
        if tag in {"VV", "VA"}:
            # kiwi는 동사/형용사도 기본형 형태소로 잘 뽑히는 편이지만,
            # 더 확실히 표준화하고 싶으면 "다" 붙여서 워드클라우드 품질 개선
            form = f"{form}다"

        form = _normalize_token_form(form)
        if not form:
            continue
        if len(form) < min_len:
            continue
        if form in _STOPWORDS:
            continue

        tokens.append(form)

    return tokens


def keyword_extract_node(state: FeedbackBoardState, top_k: int = 40) -> FeedbackBoardState:
    """
    active post들의 clean_text 기반으로
    워드클라우드 키워드 후보(top_k)를 뽑는다.
    - Kiwi 기반 형태소 분석 + 품사 필터 + 원형 정규화
    - 전체 집계 키워드는 state._tmp_wordcloud_keywords로 보관
    - 개별 글 키워드는 post.ai_analysis.keywords(최대 8개)에 보관
    """

    active_texts = []
    for p in state.posts:
        if not p.ai_analysis:
            continue
        if not p.ai_analysis.is_active:
            continue
        if p.ai_analysis.is_group_representative is not True:
            continue
        if p.ai_analysis.clean_text:
            active_texts.append(p.ai_analysis.clean_text)

    if not active_texts:
        state.warnings.append("keyword_extract_node: no active texts")
        return state

    cnt = Counter()
    for t in active_texts:
        cnt.update(_tokenize_ko_kiwi(t))

    keywords = [w for w, _ in cnt.most_common(top_k)]

    state.warnings.append(f"keyword_extract_node: extracted_keywords={len(keywords)}")

    # 개별 글 키워드(디버그/재현성/하이라이트용)
    for p in state.posts:
        if p.ai_analysis and p.ai_analysis.is_active and p.ai_analysis.clean_text:
            toks = _tokenize_ko_kiwi(p.ai_analysis.clean_text)
            p.ai_analysis.keywords = toks[:8]

    # 최종 워드클라우드 후보 저장
    state._tmp_wordcloud_keywords = keywords  # type: ignore[attr-defined]
    return state
