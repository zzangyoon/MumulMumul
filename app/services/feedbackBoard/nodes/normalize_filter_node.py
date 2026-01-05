from __future__ import annotations

from datetime import datetime
import re

from app.services.feedbackBoard.io_contract import FeedbackBoardState
from app.services.feedbackBoard.schemas import FeedbackBoardInsight


def normalize_filter_node(state: FeedbackBoardState) -> FeedbackBoardState:
    if state.posts is None:
        state.errors.append("normalize_filter_node: state.posts is None")
        return state

    cfg = state.input.config

    # ---- 강화 룰 세트 (노드 내부 상수) ----

    # 1) 욕설/공격 표현(토식 판정용) - 단어 기반 + 변형 regex
    TOXIC_WORDS = [
        # 강한 욕설
        "씨발", "시발", "ㅅㅂ", "ㅆㅂ", "시1발", "씨1발",
        "좆", "ㅈ같", "ㅈㄴ", "존나",
        "병신", "븅신", "ㅂㅅ",
        "개새끼", "개새", "새끼", "ㅅㄲ",
        "미친놈", "미친년", "미친", "미쳤",
        "꺼져", "닥쳐", "좆까",
        "죽어", "뒤져", "디져", "뒤져라",
        # 혐오/비하(필요시)
        "한남", "김치녀", "틀딱",
    ]

    TOXIC_REGEX = [
        r"ㅅ\s*[\W_]*\s*ㅂ",                     # ㅅㅂ 변형
        r"(씨|시)\s*[\W_]*\s*발",                # 씨발/시발 변형
        r"ㅂ\s*[\W_]*\s*ㅅ",                     # ㅂㅅ 변형
        r"ㅈ\s*[\W_]*\s*같",                     # ㅈ같 변형
        r"(뒤|디)\s*[\W_]*\s*져",                # 뒤져 변형
        r"개\s*[\W_]*\s*새\s*[\W_]*\s*(끼|키)",  # 개새끼 변형
    ]

    # 욕설 오탐 완화(선택): 관용구 예외
    TOXIC_EXCEPT_REGEX = [
        r"미친\s*(듯|듯이)",  # "미친 듯이 바빴다" 등
    ]

    # 2) “강제 high” 신호 (자해/자살, 타해/폭력, 협박/스토킹, 이탈/환불/법적)
    FORCE_HIGH_PATTERNS = [
        # (A) 자해/자살/극단 위험
        r"(자해|자살)",
        r"(죽|뒤|디)\s*고\s*싶",
        r"(죽|뒤|디)\s*어\s*버리",
        r"(끝내|끝내고)\s*싶",
        r"(사라지|없어지)\s*고\s*싶",
        r"(그만\s*살|살기\s*싫)",
        r"(극단적\s*선택|극단\s*선택)",
        r"(유서|목숨|목숨\s*끊)",
        r"(내가\s*없|없어졌)\s*으면",
        r"(죽을\s*것\s*같|죽겠)",  # 정책상 HIGH로 볼지 팀 합의 가능

        # (B) 타해/폭력/위협
        r"(폭행|폭력|살해|죽이)",
        r"(협박|보복|찾아가|따라가)",
        r"(칼|흉기|불\s*지르|방화)",
        r"(때려|패|조져|박살)\s*(버리|해|겠)",

        # (C) 중도 이탈/환불/법적 분쟁
        r"(중도\s*포기|포기\s*할|그만\s*두|관두|하차|탈주|퇴소|퇴학)",
        r"(환불|소송|고소|신고)\s*(하|할|함|할거)",
    ]

    # 3) 의미 없는 글(강화)
    MEANINGLESS_PATTERNS = [
        r"^[ㅋㅎ]+$",
        r"^[ㅠㅜ]+$",
        r"^[ㅋㅎㅠㅜ]+$",
        r"^[ㅇㅈㄱㅅㄴㄴㄹㅁㅂㅅㅌㅍㅎ]+$",  # 자음만(필요시 완화)
        r"^\s*$",
        r"^[\W_]+$",
        r"^(ㅇㅋ|ㅇㅇ|ㄱㅅ|ㄴㄴ|ㄱㄱ|ㄱㅊ|ㅇㅈ)$",
        r"^(ok|okay|thx|thanks|ty)$",
        r"^(별로|싫음|모름|몰라|그냥)$",
    ]

    # 4) “주의/경고” 레벨(강제 high까진 아님)
    WARNING_PATTERNS = [
        r"(힘들|버겁|지치|스트레스|멘탈|압박)",
        r"(불만|짜증|화\s*나|열받)",
        r"(불공정|차별|편애|무시|왕따)",
        r"(갈등|싸움|트러블)",
        r"(번아웃|무기력|우울|패닉|공황|불안\s*발작)",
        r"(잠을\s*못\s*자|불면)",
        r"(눈물\s*나|울컥|울고\s*싶)",
    ]

    # 5) 특정 인물/역할 공격(욕설이 없어도 high 후보)
    PERSON_ATTACK_PATTERNS = [
        r"(운영진|멘토|강사|팀장|팀원|누구)\s*(이|가)?\s*(무능|최악|싫|짜증|역겹|혐오|꺼져|죽)",
        r"(저\s*사람|그\s*사람|걔)\s*(진짜|너무)\s*(최악|싫|혐오)",
    ]

    # ---- 내부 유틸 ----
    _ws_re = re.compile(r"\s+")
    _meaningless_res = [re.compile(p) for p in MEANINGLESS_PATTERNS]
    _force_high_res = [re.compile(p) for p in FORCE_HIGH_PATTERNS]
    _warning_res = [re.compile(p) for p in WARNING_PATTERNS]
    _toxic_res = [re.compile(p) for p in TOXIC_REGEX]
    _toxic_except_res = [re.compile(p) for p in TOXIC_EXCEPT_REGEX]
    _person_attack_res = [re.compile(p) for p in PERSON_ATTACK_PATTERNS]

    # 긴 텍스트에서 반복 replace 비용 줄이기 위해,
    # 단어 기반 마스킹은 "길이 긴 단어 우선"으로 처리
    _toxic_words_sorted = sorted(set(TOXIC_WORDS), key=len, reverse=True)

    def _normalize_for_match(text: str) -> str:
        """룰 매칭용 최소 정규화: 소문자 + 공백정리."""
        t = (text or "").strip()
        t = t.lower()
        t = _ws_re.sub(" ", t)
        return t

    def _is_meaningless(text: str) -> bool:
        t = (text or "").strip()
        if len(t) <= 1:
            return True
        for rx in _meaningless_res:
            if rx.match(t):
                return True
        return False

    def _mask_toxic(text: str) -> str:
        """표시용 clean_text에서 욕설/공격 표현을 마스킹."""
        t = _normalize_for_match(text)

        # 단어 기반 마스킹
        for w in _toxic_words_sorted:
            if not w:
                continue
            t = t.replace(w.lower(), "*" * len(w))

        # regex 기반 마스킹(변형 욕설)
        # 치환 길이 통일이 어려워, 매칭 구간을 동일 길이 *로 덮음
        for rx in _toxic_res:
            def _repl(m: re.Match) -> str:
                return "*" * max(2, len(m.group(0)))
            t = rx.sub(_repl, t)

        return t

    def _has_force_high(raw_norm: str) -> bool:
        for rx in _force_high_res:
            if rx.search(raw_norm):
                return True
        return False

    def _has_warning(raw_norm: str) -> bool:
        for rx in _warning_res:
            if rx.search(raw_norm):
                return True
        return False

    def _has_person_attack(raw_norm: str) -> bool:
        for rx in _person_attack_res:
            if rx.search(raw_norm):
                return True
        return False

    def _toxicity_score(raw_norm: str) -> float:
        """
        토식 점수: 단어/정규식 히트 수 기반 스케일링 (0~1)
        - 단어 기반 히트는 1점
        - 변형 regex 히트는 1점
        - 예외(관용구)는 점수에서 일부 제외
        """
        if not raw_norm:
            return 0.0

        # 예외 처리(관용구) 존재하면, '미친' 같은 약한 트리거만으로는 점수를 낮춤
        has_except = any(rx.search(raw_norm) for rx in _toxic_except_res)

        hits = 0

        # 단어 포함 히트
        for w in _toxic_words_sorted:
            wl = w.lower()
            if wl and wl in raw_norm:
                # 관용구 예외가 있으면 "미친" 단독 히트는 제외(강한 욕설은 그대로)
                if has_except and wl in {"미친"}:
                    continue
                hits += 1

        # 변형 regex 히트
        for rx in _toxic_res:
            if rx.search(raw_norm):
                hits += 1

        # 스케일링: 0, 0.33, 0.66, 1.0에 가깝게
        # (hits가 3 이상이면 1.0)
        return min(1.0, hits / 3.0)

    # ---- main ----
    new_posts = []
    for p in state.posts:
        if p.ai_analysis is None:
            p.ai_analysis = FeedbackBoardInsight()

        raw = p.raw_text or ""
        raw_norm = _normalize_for_match(raw)

        # (1) clean_text (마스킹 포함)
        p.ai_analysis.clean_text = _mask_toxic(raw)

        # (2) meaningless → inactive (clean_text 기준)
        if _is_meaningless(p.ai_analysis.clean_text):
            p.ai_analysis.is_active = False
            if "meaningless" not in p.ai_analysis.inactive_reasons:
                p.ai_analysis.inactive_reasons.append("meaningless")
        else:
            p.ai_analysis.is_active = True

        # (3) risk scoring (원문 raw 기준)
        tox_score = _toxicity_score(raw_norm)
        p.ai_analysis.toxicity_score = tox_score
        p.ai_analysis.is_toxic = tox_score > 0.0

        force_high = _has_force_high(raw_norm)
        warning = _has_warning(raw_norm)
        person_attack = _has_person_attack(raw_norm)

        # severity 정책:
        # - 강제 high 신호: high
        # - 인물 공격 + 토식: high
        # - 토식 점수 유의미(>0): high (정책 유지)
        # - warning: medium
        # - else: low
        if force_high:
            p.ai_analysis.severity = "high"
        elif person_attack and p.ai_analysis.is_toxic:
            p.ai_analysis.severity = "high"
        elif p.ai_analysis.is_toxic:
            p.ai_analysis.severity = "high"
        elif warning:
            p.ai_analysis.severity = "medium"
        else:
            p.ai_analysis.severity = "low"

        # (4) meta
        p.ai_analysis.analyzed_at = datetime.utcnow()
        p.ai_analysis.analyzer_version = cfg.analyzer_version

        new_posts.append(p)

    state.posts = new_posts
    return state
