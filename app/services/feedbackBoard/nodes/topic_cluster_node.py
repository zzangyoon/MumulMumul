# app/services/feedbackBoard/nodes/topic_cluster_node.py

from typing import Callable, Dict, List, Any, Optional
from collections import defaultdict

import numpy as np
import json
from pydantic import BaseModel, Field

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.runnables import Runnable

from sklearn.metrics.pairwise import cosine_similarity
from sklearn.feature_extraction.text import TfidfVectorizer

from app.services.feedbackBoard.io_contract import FeedbackBoardState

class SubCategoryLLMOut(BaseModel):
    sub_category: str = Field(
        ...,
        description=(
            "클러스터 내용을 가장 잘 대표하는 sub_category 이름. "
            "운영진이 바로 이해할 수 있도록 6~20자 내외의 한국어 짧은 명사형/구문으로 작성."
        ),
    )

def _make_subcategory_llm_chain(llm: Runnable):
    parser = PydanticOutputParser(pydantic_object=SubCategoryLLMOut)
    fmt = parser.get_format_instructions()

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                (
                    "너는 부트캠프 익명 피드백을 분류하는 운영 분석 AI다.\n"
                    "- 입력에 없는 사실을 만들지 마라.\n"
                    "- 아래 excerpts에 공통으로 등장하는 핵심 이슈를 대표하는 sub_category 이름을 1개만 만들어라.\n"
                    "- 너무 추상적이면 안 되고(예: '불만'), 너무 길면 안 된다.\n"
                    "- 출력은 JSON 하나만. 추가 텍스트 금지.\n\n"
                    "{format_instructions}"
                ),
            ),
            (
                "human",
                (
                    "category_template(참고용):\n{category_template_json}\n\n"
                    "cluster excerpts(대표 문장들):\n{excerpts_json}\n\n"
                    "요구사항:\n"
                    "- sub_category: 6~20자 내외, 명사형/짧은 구문\n"
                    "- 예: '팀장 의사결정 불만', '과제 마감 압박', '공지 채널 분산'\n"
                ),
            ),
        ]
    )

    return prompt | llm | parser

def topic_cluster_node(state: FeedbackBoardState, 
    embed_fn: Callable[[List[str]], List[List[float]]],
    llm: Optional[Runnable] = None,
    *,
    max_excerpt_per_cluster: int = 5) -> FeedbackBoardState:
    """
    3-C) HDBSCAN 클러스터링 + category_template(<=5) 매핑
    - input: state.posts (split/dedup/filter 완료 가정)
    - output: post.ai_analysis.category / sub_category 채움
    """
    if state.posts is None:
        state.errors.append("topic_cluster_node: state.posts is None")
        return state
    
    # ---- 0) 대상 추리기 (active + clean_text 있는 것만) ----
    posts = state.posts

    active_posts = []
    texts = []
    for post in posts:
        if not post.ai_analysis and not post.ai_analysis.is_active and not post.ai_analysis.clean_text:
            continue

        active_posts.append(post)
        texts.append(post.ai_analysis.clean_text)

    if len(active_posts) == 0:
        state.warnings.append("topic_cluster_node: no active posts with clean_text")
        return state

    # ---- 1) 임베딩 ----
    X = np.array(embed_fn(texts), dtype=float)
    if X.ndim != 2 or X.shape[0] != len(active_posts):
        state.errors.append("topic_cluster_node: embed_fn output shape mismatch")
        return state

    # ---- 2) HDBSCAN 클러스터링 ----
    n = len(active_posts)
    if n < 2:
        # 클러스터링 불가 → 전부 하나의 카테고리로
        template = state.input.config.category_template or []
        cat = template[0] if template else "기타"

        for post in active_posts:
            post.ai_analysis.category = cat
            post.ai_analysis.sub_category = "기타"

        state.warnings.append(f"topic_cluster_node: not enough posts to cluster (n={n})")
        state.posts = posts
        return state
    
    try:
        import hdbscan  # pip install hdbscan
    except Exception as e:
        state.errors.append(f"topic_cluster_node: hdbscan import failed: {e}")
        return state

    # HDBSCAN 클러스터링
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=2,
        min_samples=1,
        metric="euclidean"
    )
    labels = clusterer.fit_predict(X)  # -1 = noise

    # ---- 3) 템플릿 카테고리 매핑 준비 ----
    template = state.input.config.category_template or []
    template_emb = None
    if template:
        template_emb = np.array(embed_fn(template), dtype=float)
        if template_emb.ndim != 2 or template_emb.shape[0] != len(template):
            state.errors.append("topic_cluster_node: template embed shape mismatch")
            return state

     # ---- 4) 클러스터 인덱스 맵 ----
    cluster_to_indices: Dict[int, List[int]] = defaultdict(list)
    for i, lab in enumerate(labels):
        cluster_to_indices[int(lab)].append(i)

    # ---- 5) sub_category 생성: LLM 체인 ----
    llm_chain = _make_subcategory_llm_chain(llm) if llm is not None else None

    def pick_excerpts(idxs: List[int], k: int = max_excerpt_per_cluster) -> List[str]:
        # 대표 문장: 간단히 clean_text 상위 k개
        # (원하면: 길이순/중요도/토픽 스코어 기반으로 개선 가능)
        ex = []
        for ii in idxs:
            t = active_posts[ii].ai_analysis.clean_text.strip()
            if t:
                ex.append(t)
        # 너무 길면 자르기
        ex = [e[:220] for e in ex]
        return ex[:k]

    def make_sub_category(label: int, idxs: List[int]) -> str:
        # noise는 일단 기타
        if label == -1:
            return "기타"

        excerpts = pick_excerpts(idxs)

        # LLM 없으면: 대표 키워드 없이 "이슈 {label}" fallback
        if llm_chain is None:
            return f"이슈 {label}"

        try:
            out: SubCategoryLLMOut = llm_chain.invoke(
                {
                    "format_instructions": PydanticOutputParser(
                        pydantic_object=SubCategoryLLMOut
                    ).get_format_instructions(),
                    "category_template_json": json.dumps(template, ensure_ascii=False),
                    "excerpts_json": json.dumps(excerpts, ensure_ascii=False),
                }
            )
            sc = (out.sub_category or "").strip()
            if sc:
                return sc
        except Exception as e:
            state.warnings.append(f"topic_cluster_node: sub_category llm failed: {e}")

        return f"이슈 {label}"

    # ---- 5) 클러스터 단위로 category_template 매핑 + 각 post에 주입 ----
    for lab, idxs in cluster_to_indices.items():
        # sub_category
        subcat = make_sub_category(lab, idxs)

        # cluster centroid
        centroid = X[idxs].mean(axis=0, keepdims=True)

        # category_template 매핑
        if template and template_emb is not None:
            sims = cosine_similarity(centroid, template_emb)[0]
            best_i = int(np.argmax(sims))
            cat = template[best_i]
        else:
            cat = "기타"

        for i in idxs:
            post = active_posts[i]
            post.ai_analysis.category = cat
            post.ai_analysis.sub_category = subcat

    state.posts = posts
    return state
