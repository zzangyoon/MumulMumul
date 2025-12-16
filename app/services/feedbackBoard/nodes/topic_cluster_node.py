# app/services/feedbackBoard/nodes/topic_cluster_node.py

from typing import Dict, List, Any
from collections import defaultdict

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.feature_extraction.text import TfidfVectorizer

from app.services.feedbackBoard.io_contract import FeedbackBoardState


def topic_cluster_node(state: FeedbackBoardState, embed_fn) -> FeedbackBoardState:
    """
    3-C) HDBSCAN 클러스터링 + category_template(<=5) 매핑
    - input: state.posts (split/dedup/filter 완료 가정)
    - output: post.ai_analysis.category / sub_category 채움
    """
    # ---- 0) 대상 추리기 (active + clean_text 있는 것만) ----
    posts = state.posts
    active_posts = []
    texts = []
    for post in posts:
        if not post.ai_analysis:
            continue
        if not post.ai_analysis.is_active:
            continue
        if not post.ai_analysis.clean_text:
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
    print(n)
    if n < 2:
        # 클러스터링 불가 → 전부 noise 취급(혹은 단일 이슈로 처리)
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

    # ---- 4) 클러스터별 sub_category 생성(간단: TF-IDF 키워드 상위) ----
    # 한국어 토큰화는 완벽하진 않지만, 지금 단계에선 “규칙 기반 placeholder”로 충분
    vec = TfidfVectorizer(
        max_features=2000,
        token_pattern=r"(?u)[\w가-힣]{2,}"  # 2글자 이상
    )
    tfidf = vec.fit_transform(texts)
    vocab = np.array(vec.get_feature_names_out())

    cluster_to_indices: Dict[int, List[int]] = defaultdict(list)
    for i, lab in enumerate(labels):
        cluster_to_indices[int(lab)].append(i)

    def pick_keywords(idxs: List[int], topk: int = 5) -> List[str]:
        if len(idxs) == 0:
            return []
        sub = tfidf[idxs].sum(axis=0)
        arr = np.asarray(sub).reshape(-1)
        top = arr.argsort()[::-1][:topk]
        kw = [str(vocab[t]) for t in top if arr[t] > 0]
        return kw[:topk]

    def make_sub_category(label: int, idxs: List[int]) -> str:
        # noise는 일단 "기타"로
        if label == -1:
            return "기타"
        kws = pick_keywords(idxs, topk=4)
        if not kws:
            return f"이슈 {label}"
        return " / ".join(kws)

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

        # 대표 요약은 weekly_context 만들 때 쓰는 값이지만
        # 여기서는 post 단위에만 주입(집계는 aggregate_weekly_context_node에서)
        for i in idxs:
            post = active_posts[i]
            post.ai_analysis.category = cat
            post.ai_analysis.sub_category = subcat

    state.posts = posts
    return state
