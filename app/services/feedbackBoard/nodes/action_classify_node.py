# app/services/feedbackBoard/nodes/action_classify_node.py
from __future__ import annotations

from typing import Literal, List
from pydantic import BaseModel, Field

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser

from app.core.models import openai_chat_model
from app.services.feedbackBoard.io_contract import FeedbackBoardState


# -----------------------------
# LLM 출력 스키마 (배치)
# -----------------------------
class ActionItem(BaseModel):
    post_id: str = Field(..., description="입력으로 받은 post_id")
    action_type: Literal["immediate", "short", "long"] = Field(
        ...,
        description="운영진 대응 긴급도"
    )
    reason: str = Field(..., description="1문장 사유(30자 내외)")


class ActionBatchOut(BaseModel):
    items: List[ActionItem] = Field(..., description="post_id별 분류 결과")


def action_classify_node(state: FeedbackBoardState) -> FeedbackBoardState:
    """
    post.ai_analysis.action_type을 채움. (LLM 배치 기반)
    - hard-rule(안전/정책): high severity 또는 toxic은 무조건 immediate
    - 나머지는 LLM이 배치로 판단하여 action_type/reason을 반환
    """
    if state.posts is None:
        state.errors.append("action_classify_node: state.posts is None")
        return state

    cfg = state.input.config
    batch_size = int(getattr(cfg, "action_batch_size", 20))  # 기본 20개 배치
    max_text_len = int(getattr(cfg, "action_max_text_len", 600))  # 배치니까 600 정도로 컷 권장

    # ---- (0) Hard-rule ----
    def _hard_immediate(p) -> bool:
        a = p.ai_analysis
        if a is None:
            return False
        if a.is_active is False:
            return False
        if a.severity == "high":
            return True
        if a.is_toxic is True:
            return True
        return False

    # ---- (1) LLM 준비 ----
    llm = openai_chat_model()

    parser = PydanticOutputParser(pydantic_object=ActionBatchOut)

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                (
                    "너는 온라인 부트캠프 운영진을 돕는 운영 분석가다.\n"
                    "여러 개의 게시글을 보고 '운영진 대응 긴급도'를 3단계로 분류한다.\n\n"
                    "분류 기준:\n"
                    "- immediate: 즉시 확인/개입 필요(운영 장애급 이슈, 분쟁/환불/퇴소, 심각한 팀갈등 폭발, 강한 인신공격 등)\n"
                    "- short: 단기 대응(일정/공지 정리/과제 가이드/난이도 완충/FAQ/멘토링 배치)\n"
                    "- long: 구조 개선(팀문화, 장기 번아웃, 커리큘럼/운영 프로세스 재설계)\n\n"
                    "규칙:\n"
                    "1) 입력에 severity=high 또는 is_toxic=true인 항목은 무조건 immediate로 분류한다.\n"
                    "2) 확신이 약하면 short로 둔다.\n"
                    "3) 반드시 모든 입력 post_id에 대해 결과를 반환한다(누락 금지).\n"
                    "4) 출력은 반드시 JSON 하나만.\n\n"
                    "{format_instructions}"
                ),
            ),
            (
                "human",
                (
                    "아래 posts를 분류해줘.\n"
                    "각 항목의 severity/is_toxic 신호를 반드시 고려해.\n\n"
                    "posts:\n{posts_json}"
                ),
            ),
        ]
    )

    chain = prompt | llm | parser

    # ---- (2) LLM 대상 모으기(하드룰 제외) ----
    targets = []
    for p in state.posts:
        if not p.ai_analysis:
            continue
        if not p.ai_analysis.is_active:
            continue

        if _hard_immediate(p):
            p.ai_analysis.action_type = "immediate"
            if hasattr(p.ai_analysis, "action_reason"):
                p.ai_analysis.action_reason = "high/toxic rule"
            continue

        text = (p.ai_analysis.clean_text or p.raw_text or "").strip()
        if not text:
            p.ai_analysis.action_type = "short"
            if hasattr(p.ai_analysis, "action_reason"):
                p.ai_analysis.action_reason = "empty text"
            continue

        targets.append(
            {
                "post_id": p.post_id,
                "post_text": text[:max_text_len],
                "severity": p.ai_analysis.severity or "low",
                "is_toxic": bool(p.ai_analysis.is_toxic),
                "toxicity_score": float(p.ai_analysis.toxicity_score or 0.0),
                "category": p.ai_analysis.category or "",
                "sub_category": p.ai_analysis.sub_category or "",
            }
        )

    if not targets:
        return state

    # ---- (3) 배치 호출 + 결과 매핑 ----
    # post_id -> (action_type, reason)
    result_map = {}

    for i in range(0, len(targets), batch_size):
        batch = targets[i : i + batch_size]

        try:
            out: ActionBatchOut = chain.invoke(
                {
                    "format_instructions": parser.get_format_instructions(),
                    "posts_json": batch,  # LangChain이 dict/list를 문자열로 렌더링
                }
            )

            for item in out.items:
                result_map[item.post_id] = (item.action_type, item.reason)

        except Exception as e:
            # 배치 실패 시: 전부 short로 fallback (보수적)
            state.warnings.append(f"action_classify_node: batch_failed_fallback: {e}")
            for b in batch:
                result_map[b["post_id"]] = ("short", "llm_failed_batch_fallback")

    # ---- (4) state.posts에 반영 ----
    for p in state.posts:
        if not p.ai_analysis or not p.ai_analysis.is_active:
            continue
        if p.ai_analysis.action_type is not None:
            # hard-rule/empty 처리된 애들은 이미 세팅됨
            continue

        v = result_map.get(p.post_id)
        if v is None:
            # 누락 방지: short 기본
            p.ai_analysis.action_type = "short"
            if hasattr(p.ai_analysis, "action_reason"):
                p.ai_analysis.action_reason = "missing_in_llm_output"
            continue

        action_type, reason = v
        p.ai_analysis.action_type = action_type
        if hasattr(p.ai_analysis, "action_reason"):
            p.ai_analysis.action_reason = reason

    return state
