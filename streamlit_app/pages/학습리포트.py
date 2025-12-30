import streamlit as st
import pandas as pd
import altair as alt

from streamlit_app.api.curriculum import (
    analyze_curriculum_text,
    create_curriculum_report,
    fetch_curriculum_report,
    fetch_curriculum_config,
    save_curriculum_config,
)
from streamlit_app.api.camp import fetch_camps

st.set_page_config(
    page_title="학습 리포트", layout="wide")
st.title("학습 리포트", text_alignment = "center")

# 리포트 가이드
def render_curriculum_analysis_rules():
    """커리큘럼 난이도 & 추가 학습 요구 분석 기준 안내 블록."""
    st.markdown("""
        ### 📐 커리큘럼 분석이 따르는 핵심 기준

        **1️⃣ 어려운 파트(커리큘럼 내) 판단 기준**
        - 해당 주차 질문 중 **20% 이상**을 차지하거나  
        - 질문 수 **Top 3 카테고리**이거나  
        - “개념 이해 혼란” 패턴이 많이 발생하면  
        → 난이도가 높다고 판단합니다.

        ---

        **2️⃣ 커리큘럼 외 추가 요구 판단 기준**
        - 같은 주제가 **2회 이상 반복 질문**되거나  
        - 전체 질문 중 **15% 이상**이면  
        → 별도로 다뤄야 하는 주요 요구로 간주합니다.

        ---

        **3️⃣ 즉시 보완 vs 다음 기수 개선**
        - **즉시 보완:** Week 1–2 기초 파트에서 질문 비중이 높거나 혼란이 반복될 때  
        - **다음 기수 개선:** 심화 개념 또는 구조적 개선이 필요한 항목

        ---

        AI 인사이트는 위 기준을 기반으로  
        “어디가 어려웠는지, 어떤 보완이 필요한지, 무엇을 새로 제공해야 하는지”를 정리합니다.
    """)


# --------------------------------
# 0) 세션 기반 데이터 캐시 설정  🔥
# --------------------------------
if "curriculum_session" not in st.session_state:  # 한 번만 초기화
    st.session_state["curriculum_session"] = {
        "curriculum_config_by_camp": {},    # {camp_id: config}
        "curriculum_reports": {},           # {f"{camp_id}_{week_index}": payload}
    }

session_cache = st.session_state["curriculum_session"]
camp_session_cache = st.session_state["camp_session"]
camps = camp_session_cache["camps"]
camp_name_to_id = camp_session_cache["camp_name_to_id"]

# --------------------------------
# 1) 캠프 목록 / 주차 선택
# --------------------------------
st.sidebar.header("필터 설정")

camp_name = st.sidebar.selectbox("반 선택", list(camp_name_to_id.keys()))
camp_id = camp_name_to_id[camp_name]
camp = camps[camp_id]
camp_start_date = camp.get("start_date")
camp_end_date = camp.get("end_date")

weeks = [f"{i} 주차" for i in range(1, camp["total_weeks"] + 1)]
selected_week_label = st.sidebar.selectbox("주차 선택", weeks)
week_index = int(selected_week_label.split()[0])  # "Week 3" -> 3
week_label = f"{week_index}주차"

# --------------------------------
# 1-1) 리포트 생성 버튼 + 세션 캐싱
# --------------------------------
report_key = f"{camp_id}_{week_index}"
reports_cache = session_cache["curriculum_reports"]


# 1) 세션에서 먼저 찾기
payload = reports_cache.get(report_key)

# 2) 세션에 없으면 → 백엔드(DB)에서 한 번 조회해서 있으면 캐시
if payload is None:
    db_report = fetch_curriculum_report(camp_id=camp_id, week_index=week_index)
    if db_report is not None:
        payload = db_report
        reports_cache[report_key] = payload
    else:
        payload = None

generate_clicked = st.sidebar.button("리포트 생성하기")
if generate_clicked:
    with st.spinner("리포트 생성 중입니다..."):
        payload = create_curriculum_report(
            camp_id=camp_id,
            week_index=week_index,
        )
        session_cache["curriculum_reports"][report_key] = payload

# 세션에서 현재 선택된 캠프/주차의 리포트 가져오기
payload = session_cache["curriculum_reports"].get(report_key)

# --------------------------------
# 2) 리포트 payload 사용
# --------------------------------
summary = payload.get("summary_cards") if payload else None
charts = payload.get("charts") if payload else {}
tables = payload.get("tables") if payload else {}
ai_insights = payload.get("ai_insights") if payload else {}
raw_stats = payload.get("raw_stats", {}) if payload else {}

# ================================
# DataFrame 변환 유틸
# ================================
# 1) 카테고리별 질문 수 (차트용)
df_cat_raw = pd.DataFrame(charts.get("questions_by_category", []))  # [{category, scope, question_count}, ...]

if not df_cat_raw.empty:
    # scope 무시하고 카테고리별 총합으로 집계
    df_categories = (
        df_cat_raw.groupby("category", as_index=False)["question_count"]
        .sum()
        .rename(columns={"question_count": "question_count"})
        .sort_values("question_count", ascending=False)
    )
else:
    df_categories = pd.DataFrame(columns=["category", "question_count"])

# 2) 분류별 질문 리스트 (pattern_tags, intent는 지금은 없음 → TODO)
question_rows = []
for block in tables.get("questions_grouped_by_category", []):
    category = block.get("category")
    scope = block.get("scope")
    for q in block.get("questions", []):
        question_rows.append(
            {
                "category": category,
                "scope": scope,
                "question_text": q.get("question_text"),
                "created_at": q.get("created_at"),
                "pattern_tags": q.get("pattern_tags") or [],
                "intent": q.get("intent"),
            }
        )

df_questions = pd.DataFrame(question_rows)

# 3) 커리큘럼 외 질문 리스트
df_outer = pd.DataFrame(
    [
        {
            "category": q.get("category"),
            "question_text": q.get("question_text"),
            "created_at": q.get("created_at"),
        }
        for q in tables.get("curriculum_out_questions", [])
    ]
)

# 4) 패턴 전체 분포
pattern_stats = raw_stats.get("pattern_stats", [])

df_pattern_overall = pd.DataFrame(pattern_stats)

# 5) 카테고리별 주요 패턴
cat_pattern_raw = raw_stats.get("category_pattern_summary", [])
category_pattern_summary = []
for row in cat_pattern_raw:
    if row.get("patterns"):
        pattern_str = ", ".join(
            f"{p['tag']}({p['count']})" for p in row["patterns"]
        )
    else:
        pattern_str = ""
    category_pattern_summary.append(
        {
            "category": row["category"],
            "patterns": pattern_str,
            "summary": "",  # 나중에 LLM이 한 줄 요약 채워주게 해도 됨
        }
    )

# 6) 커리큘럼 강화 우선순위
priority_rows = ai_insights.get("priority", [])
df_priority = pd.DataFrame(priority_rows)

# =========================================================
# 이번 주 리포트
# =========================================================
st.subheader(f"[{camp_name}] {week_label} 학습 리포트", text_alignment="center")
st.markdown(f"{camp_start_date} ~ {camp_end_date} 학습 챗봇에 올라온 글을 분석한 결과입니다.", text_alignment="center")

# ================================
# 탭 구성
# ================================
tab_summary, tab_ai, tab_detail = st.tabs(
    ["📊 요약 리포트", "📃 AI 리포트", "📂 상세 데이터"]
)

# =========================================================
# (1) 요약 탭
# =========================================================
with tab_summary:
    st.subheader(f"📌 {week_label} 요약 ({camp_name})")
    if not payload or not summary:
        st.info(
            f"현재 **{camp_name} / {week_label}** 리포트가 없습니다.\n\n"
            "좌측 사이드바에서 **'리포트 생성하기'** 버튼을 눌러 리포트를 생성해 주세요."
        )
        # 여기서 return 또는 그냥 아래 코드 실행 안 되게 if/else 로 감싸기
    else:
        total_questions = summary.get("total_questions", 0)
        out_ratio = summary.get("curriculum_out_ratio", 0.0) * 100  # 0~1 → %
        in_q = summary.get("curriculum_in_questions", 0)
        out_q = summary.get("curriculum_out_questions", 0)
        num_categories = df_categories["category"].nunique() if not df_categories.empty else 0

        # 1. 상단 Summary Cards
        st.markdown("### 🔢 핵심 지표")

        col1, col2, col3 = st.columns(3)
        col1.metric("전체 질문 수", f"{total_questions}건")
        col2.metric("커리큘럼 외 비율", f"{out_ratio:.1f}%")
        col3.metric("질문 분류 수", f"{num_categories}개")

        # 2. 상위 질문 분류 Top 3
        st.markdown("### 🔥 상위 질문 분류 Top 3")

        top_cats = summary.get("top_question_categories", [])[:3]

        colA, colB, colC = st.columns(3)
        cols = [colA, colB, colC]

        for col, cat in zip(cols, top_cats):
            scope_label = "커리큘럼 내" if cat["scope"] == "in" else "커리큘럼 외"
            col.info(
                f"**{cat['category']}**  \n"
                f"{int(cat['question_count'])}건  \n"
                f"*{scope_label}*"
            )
        
        st.markdown("---")

        # 3. 질문 패턴 분포 (전체)
        st.markdown("### 🧩 이번 주 질문 패턴 분포")

        if not df_pattern_overall.empty:
            chart_pattern = (
                alt.Chart(df_pattern_overall)
                .mark_bar()
                .encode(
                    x=alt.X("count:Q", title="질문 수"),
                    y=alt.Y("tag:N", sort="-x", title="패턴 태그"),
                    tooltip=[
                        "tag",
                        "count",
                        alt.Tooltip("ratio:Q", format=".0%"),
                    ],
                )
                .properties(height=220)
            )
            st.altair_chart(chart_pattern, use_container_width=True)

            top_tag_row = df_pattern_overall.sort_values("count", ascending=False).iloc[0]
            st.caption(
                f"→ 이번 주에는 **{top_tag_row['tag']}** 패턴의 질문이 가장 많이 관찰되었음."
            )
        else:
            st.write("패턴 통계 데이터가 없습니다.")

        st.markdown("---")

        # 4. 커리큘럼 강화 우선순위 Top 3
        st.markdown("### 🧱 커리큘럼 강화 우선순위 Top 3")

        priority_map = {}
        if not df_priority.empty:
            for _, r in df_priority.iterrows():
                main_patterns = r.get("main_patterns") or []
                if isinstance(main_patterns, list):
                    main_patterns_str = ", ".join(main_patterns)
                else:
                    main_patterns_str = str(main_patterns) if main_patterns else ""

                priority_map[r["category"]] = {
                    "rank": r.get("rank"),
                    "difficulty_level": r.get("difficulty_level"),
                    "main_patterns": main_patterns_str,
                    "action_hint": r.get("action_hint") or "",
                }
            
            st.dataframe(
                df_priority[
                    ["rank", "category", "difficulty_level", "main_patterns", "action_hint"]
                ],
                hide_index=True,
            )
        else:
            st.write("강화 우선순위 데이터가 없습니다.")
        
        st.markdown("---")

        # 5. 카테고리별 주요 어려움 패턴
        # 우선순위 / 난이도 매핑 (category 기준)
        priority_level_by_category = {}
        priority_rank_by_category = {}
        action_hint_by_category = {}

        if not df_priority.empty:
            severity_rank = {"high": 3, "medium": 2, "low": 1}

            for _, row_p in df_priority.iterrows():
                cat = row_p.get("category")
                level_raw = row_p.get("difficulty_level", "low")
                if not cat:
                    continue
                level = str(level_raw).lower()
                priority_level_by_category[cat] = level
                # rank가 있으면 같이 써줘도 됨 (없으면 난이도로만)
                if "rank" in row_p:
                    priority_rank_by_category[cat] = row_p["rank"]
                
                # 액션 힌트 저장
                action_hint = row_p.get("action_hint") or ""
                action_hint_by_category[cat] = action_hint

            # 6. 카테고리별 주요 어려움 패턴
            st.markdown("### 🧠 카테고리별 주요 어려움 패턴")

            if category_pattern_summary:
                # 1) 우선순위 높은 순으로 정렬 (난이도 high > medium > low, 그다음 rank, 그다음 이름)
                def _severity_score(cat: str) -> int:
                    level = priority_level_by_category.get(cat, "low")
                    return {"high": 3, "medium": 2, "low": 1}.get(level, 1)

                def _rank_score(cat: str) -> int:
                    # rank가 작을수록 우선순위 높음 → 없는 경우는 큰 값으로 밀어주기
                    return priority_rank_by_category.get(cat, 999)

                sorted_patterns = sorted(
                    category_pattern_summary,
                    key=lambda r: (
                        -_severity_score(r["category"]),  # 난이도 높은 것 먼저
                        _rank_score(r["category"]),       # rank 1, 2, 3 순
                        r["category"],                    # 이름순
                    ),
                )

                # 2) 3 컬럼으로 세로 배치
                cols = st.columns(3)

                for idx, row in enumerate(sorted_patterns):
                    col = cols[idx % 3]  # 0,1,2 / 0,1,2 / ... 반복
                    cat = row["category"]
                    patterns = row["patterns"]

                    level = priority_level_by_category.get(cat, "low")
                    level_label = {
                        "high": "HIGH",
                        "medium": "MEDIUM",
                        "low": "LOW",
                    }.get(level, "LOW")

                    # 박스 헤더 텍스트
                    header_text = f"**{cat}**  \n난이도: {level_label}"

                    with col:
                        # 난이도에 따라 강조 스타일 다르게
                        if level == "high":
                            st.error(header_text)
                        elif level == "medium":
                            st.warning(header_text)
                        else:
                            st.info(header_text)

                        st.markdown(f"- 주요 패턴: {patterns}")
                        
                        # 액션 힌트 (있을 때만)
                        hint = action_hint_by_category.get(cat)
                        if hint:
                            st.markdown(f"- 개선 방향: {hint}")
                        
                        if row.get("summary"):
                            st.markdown(f"- 요약: {row['summary']}")
                        st.markdown("")
            else:
                st.write("카테고리별 패턴 요약 데이터가 없습니다.")


        st.markdown("---")

        # 6. 커리큘럼 외 주요 토픽
        st.markdown("### 🧭 커리큘럼 외 주요 토픽")

        extra_topics = ai_insights.get("extra_topics_detail", []) or []

        # 커리큘럼 외 질문이 실제로 없으면 강제로 비우기
        if df_outer.empty or summary.get("curriculum_out_questions", 0) == 0:
            extra_topics = []

        if extra_topics:
            n_cols = 3
            cols = st.columns(n_cols)

            for idx, t in enumerate(extra_topics):
                col = cols[idx % n_cols]   # ✅ 0,1,2 / 0,1,2 ... 로 순환
                with col:
                    with st.container(border=True):
                        st.markdown(f"#### {t['topic_label']} ({t['question_count']}건)")
                        if t.get("example_questions"):
                            st.markdown(f"- 대표 질문: {t['example_questions'][0]}")
                        if t.get("suggested_session_idea"):
                            st.markdown(f"- 제안: {t['suggested_session_idea']}")
                        st.markdown("")
        else:
            st.write("커리큘럼 외 질문이 없습니다.")

# =========================================================
# (2) AI 심층 분석 탭
# =========================================================
with tab_ai:
    st.subheader(f"🤖 AI 심층 분석 — {week_label} ({camp_name})")

    if not payload or not summary:
        st.info(
            f"현재 **{camp_name} / {week_label}** 리포트가 없습니다.\n\n"
            "좌측 사이드바에서 **'리포트 생성하기'** 버튼을 눌러 리포트를 생성해 주세요."
        )
        # 여기서 return 또는 그냥 아래 코드 실행 안 되게 if/else 로 감싸기
    else:
        with st.container():
            with st.expander("🔎 AI 분석 기준 보기", expanded=False):
                render_curriculum_analysis_rules()

        colA, colB, colC = st.columns(3)

        with colA:
            st.markdown("#### 🔥 가장 어려운 파트 요약")
            st.info(ai_insights.get("hardest_part_summary", "가장 어려운 파트 요약 없음"))

        with colB:
            st.markdown("#### 🧩 커리큘럼 외 질문 요약")
            st.warning(ai_insights.get("curriculum_out_summary", "커리큘럼 외 질문 요약 없음"))

        with colC:
            st.markdown("#### 🛠 개선 방향 요약")
            st.success(ai_insights.get("improvement_summary", "개선 방향 요약 없음"))

        st.markdown("---")

        st.markdown("## 📄 AI 인사이트 상세 보고서")

        # 1) 이번 주 가장 어려워한 파트
        st.markdown("### 1. 이번 주 가장 어려워한 파트")

        hardest_parts = ai_insights.get("hardest_parts_detail", [])
        if hardest_parts:
            for block in hardest_parts:
                st.markdown(f"#### • {block['part_label']}")
                if block.get("main_categories"):
                    st.markdown("- 주요 분류: " + ", ".join(block["main_categories"]))
                if block.get("example_questions"):
                    st.markdown("**예시 질문**")
                    for q in block["example_questions"]:
                        st.markdown(f"- {q}")
                if block.get("root_cause_analysis"):
                    st.markdown("**원인 분석**")
                    st.markdown(block["root_cause_analysis"])
                if block.get("improvement_direction"):
                    st.markdown("**개선 방향**")
                    st.markdown(block["improvement_direction"])
                st.markdown("---")
        else:
            st.write("어려운 파트에 대한 상세 분석이 없습니다.")

        # 2) 커리큘럼 외 질문 분석
        st.markdown("### 2. 커리큘럼 외 질문 분석")

        extra_topics = ai_insights.get("extra_topics_detail", [])
        if extra_topics:
            for topic in extra_topics:
                st.markdown(f"#### • {topic['topic_label']} ({topic['question_count']}건)")
                if topic.get("example_questions"):
                    st.markdown("**예시 질문**")
                    for q in topic["example_questions"]:
                        st.markdown(f"- {q}")
                if topic.get("suggested_session_idea"):
                    st.markdown("**추가 세션/자료 제안**")
                    st.markdown(topic["suggested_session_idea"])
                st.markdown("---")
        else:
            st.write("커리큘럼 외 질문에 대한 상세 분석이 없습니다.")

        # 3) 운영진 액션 정리
        st.markdown("### 3. 운영진 액션 정리")

        st.markdown("#### 3-1. 커리큘럼/난이도 개선 액션")
        st.markdown(ai_insights.get("curriculum_improvement_actions", "내용 없음"))

        st.markdown("#### 3-2. 커리큘럼 외 세션/자료 제안")
        st.markdown(ai_insights.get("extra_session_suggestions", "내용 없음"))



# =========================================================
# (3) 상세 데이터 탭
# =========================================================
with tab_detail:
    st.markdown("#### 📊 카테고리별 질문 수")

    if not df_categories.empty:
        chart_cat = (
            alt.Chart(df_categories)
            .mark_bar()
            .encode(
                x=alt.X("question_count:Q", title="질문 수"),
                y=alt.Y("category:N", sort="-x", title="질문 분류"),
                tooltip=["category", "question_count"],
            )
            .properties(height=260)
        )
        st.altair_chart(chart_cat, use_container_width=True)
    else:
        st.write("질문 데이터가 없습니다.")

    # 7-2. 분류별 질문 리스트 (pattern + intent 포함)
    st.markdown("#### 📋 카테고리별 질문 리스트")

    if not df_categories.empty and not df_questions.empty:
        selected_cat = st.selectbox(
            "분류 선택",
            df_categories["category"].tolist(),
            key="category_select_detail",
        )

        df_q_cat = df_questions[df_questions["category"] == selected_cat]

        for _, row in df_q_cat.iterrows():
            st.markdown(f"**{row['question_text']}**")
            st.markdown(
                f"  - 질문 의도: {row['intent']}  \n"
                f"  - 태그: {', '.join(row['pattern_tags'])}"
            )
    else:
        st.write("표시할 질문이 없습니다.")

    st.markdown("---")

    # 7-3. 커리큘럼 내/외 비율 파이
    st.markdown("#### 📉 커리큘럼 내/외 질문 비율")

    scope_ratio = charts.get("curriculum_scope_ratio", [])
    if scope_ratio:
        df_ratio = pd.DataFrame(
            [
                {
                    "type": "커리큘럼 내" if r["scope"] == "in" else "커리큘럼 외",
                    "count": r["question_count"],
                }
                for r in scope_ratio
            ]
        )

        pie = (
            alt.Chart(df_ratio)
            .mark_arc(innerRadius=40)
            .encode(
                theta="count:Q",
                color="type:N",
                tooltip=["type", "count"],
            )
            .properties(height=260)
        )
        st.altair_chart(pie, use_container_width=True)
    else:
        st.write("커리큘럼 내/외 데이터가 없습니다.")

    st.markdown("#### 커리큘럼 외 질문 전체 리스트")

    if not df_outer.empty:
        for q in df_outer["question_text"]:
            st.markdown(f"- {q}")
    else:
        st.write("커리큘럼 외 질문이 없습니다.")