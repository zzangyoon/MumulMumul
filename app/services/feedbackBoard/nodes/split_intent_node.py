# app/services/feedbackBoard/nodes/split_intent_node.py
import sys
from pathlib import Path

from app.core.models import openai_chat_model

# 이 파일 기준으로 프로젝트 루트 계산
CURRENT_FILE = Path(__file__).resolve()
ROOT_DIR = CURRENT_FILE.parents[4]   # .../MumulMumul
sys.path.append(str(ROOT_DIR))

from typing import List, Dict
from datetime import datetime
import re

from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser

from app.services.feedbackBoard.schemas import FeedbackBoardPost, FeedbackBoardInsight
from app.services.feedbackBoard.io_contract import FeedbackBoardState


# -----------------------------
# LLM 출력 스키마 (배치)
# -----------------------------
class SplitItem(BaseModel):
    post_id: str = Field(..., description="입력으로 받은 post_id")
    should_split: bool = Field(..., description="분리 필요 여부")
    segments: List[str] = Field(..., description="분리된 세그먼트(없으면 빈 리스트)")


class SplitBatchOut(BaseModel):
    items: List[SplitItem] = Field(..., description="post_id별 split 결과")


def split_intent_node(state: FeedbackBoardState) -> FeedbackBoardState:
    """
    하나의 글에 서로 다른 의미 축(카테고리 가능성)이 있을 경우 split
    - LLM 배치 기반 판단/분리 (보수적으로)
    - 원본(parent)은 반드시 남기되 비활성화(is_active=False)
    """
    if not state.posts:
        state.warnings.append("split_intent_node: state.posts is empty")
        return state

    cfg = state.input.config
    max_parts = int(getattr(cfg, "split_max_parts", 5))
    batch_size = int(getattr(cfg, "split_batch_size", 20))
    max_text_len = int(getattr(cfg, "split_max_text_len", 800))  # 배치 입력이므로 800 권장

    # ---- (0) LLM 준비 ----
    llm = openai_chat_model()
    parser = PydanticOutputParser(pydantic_object=SplitBatchOut)

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                (
                    "너는 온라인 부트캠프 익명 피드백 글을 '의미 축' 기준으로 분리하는 분석기다.\n"
                    "여러 게시글을 한 번에 처리한다.\n\n"
                    "분리 기준(보수적으로):\n"
                    "- 서로 다른 대상/영역(운영/커리큘럼/프로젝트/학습/팀)이 섞인 경우\n"
                    "- 같은 영역이라도 전혀 다른 이슈가 병렬로 나열된 경우\n"
                    "분리하지 말아야 하는 경우:\n"
                    "- 같은 이슈를 부연/예시/감정표현으로 이어가는 경우\n"
                    "- 문장 수는 많지만 사실상 하나의 요청/불만인 경우\n\n"
                    "규칙:\n"
                    "- 각 post_id에 대해 반드시 결과를 반환(누락 금지)\n"
                    "- should_split=false면 segments는 []\n"
                    "- segments는 원문 의미를 유지한 문장 단위(독립적으로 이해 가능)\n"
                    f"- segments 최대 {max_parts}개\n"
                    "- 출력은 반드시 JSON 하나만 (추가 텍스트 금지)\n\n"
                    "{format_instructions}"
                ),
            ),
            (
                "human",
                (
                    "아래 posts를 기준에 맞게 split 여부와 segments를 출력해줘.\n\n"
                    "posts:\n{posts_json}"
                ),
            ),
        ]
    )

    chain = prompt | llm | parser

    # ---- fallback split(LLM 실패 시) ----
    split_patterns = [
        r"(?:그리고|근데|하지만|또한|한편)\s*",
        r"(?:\n|[.?!])\s*",
    ]

    def _fallback_split(text: str) -> List[str]:
        segments = [text]
        for pat in split_patterns:
            tmp = []
            for seg in segments:
                tmp.extend([s.strip() for s in re.split(pat, seg) if s.strip()])
            segments = tmp
        if len(segments) <= 1:
            return []
        return segments[:max_parts]

    def _normalize_segments(segs: List[str], original: str) -> List[str]:
        out = []
        orig = (original or "").strip()
        seen = set()
        for s in segs or []:
            t = (s or "").strip()
            t = re.sub(r"\s+", " ", t)
            if not t:
                continue
            if len(t) < 6:
                continue
            if t == orig:
                continue
            if t in seen:
                continue
            seen.add(t)
            out.append(t)
            if len(out) >= max_parts:
                break
        return out

    # ---- (1) 대상 모으기 (active만) ----
    # post_id -> original post 참조를 위한 맵
    post_map: Dict[str, FeedbackBoardPost] = {}
    targets = []

    for post in state.posts:
        analysis = post.ai_analysis
        if analysis is None or not analysis.is_active:
            continue

        clean_text = (analysis.clean_text or "").strip()
        if not clean_text:
            continue

        post_map[post.post_id] = post
        targets.append(
            {
                "post_id": post.post_id,
                "text": clean_text[:max_text_len],
            }
        )

    # active 대상이 없으면 그대로 리턴
    if not targets:
        return state

    # ---- (2) 배치 호출하여 결과 맵 생성 ----
    result_map: Dict[str, SplitItem] = {}

    for i in range(0, len(targets), batch_size):
        batch = targets[i : i + batch_size]
        try:
            out: SplitBatchOut = chain.invoke(
                {
                    "format_instructions": parser.get_format_instructions(),
                    "posts_json": batch,
                }
            )
            for item in out.items:
                result_map[item.post_id] = item

            # 누락 방지: 혹시 특정 post_id가 빠지면 fallback으로 채움
            batch_ids = {b["post_id"] for b in batch}
            returned_ids = {it.post_id for it in out.items}
            missing = batch_ids - returned_ids
            for mid in missing:
                t = next((b["text"] for b in batch if b["post_id"] == mid), "")
                segs = _normalize_segments(_fallback_split(t), t)
                result_map[mid] = SplitItem(post_id=mid, should_split=len(segs) > 0, segments=segs)

        except Exception as e:
            state.warnings.append(f"split_intent_node: batch_llm_failed_fallback: {e}")
            # 배치 전체 fallback
            for b in batch:
                t = b["text"]
                segs = _normalize_segments(_fallback_split(t), t)
                result_map[b["post_id"]] = SplitItem(
                    post_id=b["post_id"],
                    should_split=len(segs) > 0,
                    segments=segs,
                )

    # ---- (3) 결과 반영: parent 비활성화 + child 생성 ----
    new_posts: List[FeedbackBoardPost] = []

    for post in state.posts:
        analysis = post.ai_analysis
        if analysis is None or not analysis.is_active:
            new_posts.append(post)
            continue

        clean_text = (analysis.clean_text or "").strip()
        if not clean_text:
            new_posts.append(post)
            continue

        res = result_map.get(post.post_id)
        if res is None or (not res.should_split) or (len(res.segments) <= 0):
            new_posts.append(post)
            continue

        segments = _normalize_segments(res.segments, clean_text)
        if len(segments) <= 0:
            new_posts.append(post)
            continue

        # parent 유지 + 비활성화
        parent_post = post
        parent_post.ai_analysis.is_active = False
        if "split_parent" not in parent_post.ai_analysis.inactive_reasons:
            parent_post.ai_analysis.inactive_reasons.append("split_parent")
        new_posts.append(parent_post)

        # children 생성
        for idx, seg in enumerate(segments[:max_parts]):
            base = analysis.model_copy(deep=True) if analysis else FeedbackBoardInsight()

            base.clean_text = seg
            base.parent_post_id = post.post_id
            base.is_split_child = True
            base.split_index = idx
            base.is_active = True
            base.inactive_reasons = []

            child = FeedbackBoardPost(
                post_id=f"{post.post_id}_split_{idx}",
                camp_id=post.camp_id,
                author_id=post.author_id,
                raw_text=seg,
                created_at=post.created_at,
                ai_analysis=base,
                parent_post_id=post.post_id,
            )
            new_posts.append(child)

    state.posts = new_posts
    return state


if __name__ == "__main__":
    from app.services.feedbackBoard.io_contract import PipelineInput, RunConfig

    post = FeedbackBoardPost(
        post_id="p1",
        camp_id=1,
        author_id=101,
        raw_text="팀장이 의견을 안 들어요. 그리고 공지 채널도 너무 복잡해요.",
        created_at=datetime.utcnow(),
        ai_analysis=FeedbackBoardInsight(
            clean_text="팀장이 의견을 안 들어요. 그리고 공지 채널도 너무 복잡해요.",
            is_active=True,
            analyzer_version="fb_v1",
        ),
    )

    state = FeedbackBoardState(
        input=PipelineInput(config=RunConfig(camp_id=1, week=1, split_max_parts=5)),
        raw_posts=[],
        posts=[post],
        weekly_context=None,
        weekly_report=None,
        final=None,
        warnings=[],
        errors=[],
    )

    out = split_intent_node(state)

    parents = [p for p in out.posts if p.post_id == "p1"]
    children = [p for p in out.posts if p.post_id.startswith("p1_split")]

    assert len(parents) == 1
    assert parents[0].ai_analysis.is_active is False
    assert len(children) >= 1
    assert children[0].ai_analysis.is_split_child is True
    assert children[0].ai_analysis.parent_post_id == "p1"

    print("✅ split_intent_node batch standalone test passed")
