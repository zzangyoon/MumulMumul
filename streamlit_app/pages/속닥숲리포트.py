import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
from datetime import datetime, timedelta

from streamlit_app.api.feedback import create_feedback_report, fetch_feedback_report
from streamlit_app.container.chart import draw_wordcloud, make_ratio_gauge


# ============================================
# 페이지 기본 설정
# ============================================
st.set_page_config(
    page_title="속닥숲 리포트",
    page_icon="🌲",
    layout="wide"
)
st.title("속닥숲 리포트", text_alignment="center")


# --------------------------------
# 0) 세션 기반 데이터 캐시 설정
# --------------------------------
if "feedback_session" not in st.session_state:  # 한 번만 초기화
    st.session_state["feedback_session"] = {
        "feedback_reports": {},  # {f"{camp_id}_{week_index}": report_payload}
    }

session_cache = st.session_state["feedback_session"]

# 캠프 세션(기존 너희 프로젝트 캐시 가정)
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

weeks = [f"{i} 주차" for i in range(1, camp["total_weeks"] + 1)]
selected_week_label = st.sidebar.selectbox("주차 선택", weeks)
week_index = int(selected_week_label.split()[0])  # "3 주차" -> 3
week_label = f"{week_index} 주차"

camp_start_date = camp["start_date"]
camp_end_date = camp["end_date"]


# --------------------------------
# 1-1) 리포트 조회/생성 + 세션 캐싱
# --------------------------------
report_key = f"{camp_id}_{week_index}"
reports_cache = session_cache["feedback_reports"]

# 1) 세션에서 먼저 찾기
payload = reports_cache.get(report_key)

# 2) 세션에 없으면 → 백엔드(DB)에서 한 번 조회해서 있으면 캐시
if payload is None:
    db_report = fetch_feedback_report(camp_id=camp_id, week_index=week_index)
    if db_report is not None:
        payload = db_report
        reports_cache[report_key] = payload

generate_clicked = st.sidebar.button("리포트 생성하기")
if generate_clicked:
    with st.spinner("리포트 생성 중입니다..."):
        payload = create_feedback_report(
            camp_id=camp_id,
            week_index=week_index,
        )
        reports_cache[report_key] = payload

# 최신 payload 다시 로딩
payload = reports_cache.get(report_key)

if not payload:
    st.info("아직 리포트가 없습니다. 좌측에서 '리포트 생성하기'를 눌러주세요.")
    st.stop()


report = payload

week_summary = report.get("week_summary" "이번 주 속닥숲 요약 정보가 없습니다.")
stats = report.get("stats", {}) or {}
wordcloud = report.get("wordcloud", {}) or {}

key_topics = report.get("key_topics", []) or []
ops_actions = report.get("ops_actions", []) or []

# logs는 "표시(하이라이트/드릴다운)" 용도로만 사용
logs_df = pd.DataFrame(report.get("logs", []))

# 드릴다운/하이라이트에서 필요한 컬럼이 없을 수도 있으니 보정
for col, default in [
    ("post_id", None),
    ("severity", "low"),
    ("is_toxic", False),
    ("created_at", None),
    ("clean_text", ""),
    ("raw_text", ""),
    ("user_id", None),
    ("summary", ""),
    ("category", "Unknown"),
    ("sub_category", "Unknown"),
    ("parent_post_id", None),
]:
    if col not in logs_df.columns:
        logs_df[col] = default

# created_at 파싱(문자열일 경우)
if logs_df["created_at"].dtype == object:
    logs_df["created_at"] = pd.to_datetime(logs_df["created_at"], errors="coerce")

# =========================================================
# 이번 주 리포트
# =========================================================
st.subheader(f"[{camp_name}] {week_label} 속닥숲 리포트", text_alignment="center")
st.markdown(f"{camp_start_date} ~ {camp_end_date} 속닥숲에 올라온 글을 분석한 결과입니다.", text_alignment="center")
st.markdown("---")


# =========================================================
# 🚨 위험/주의 요약 (stats 기반)
# =========================================================
total_posts = int(stats.get("total_posts", 0))
toxic_posts = int(stats.get("toxic_posts", 0))
toxic_ratio = float(stats.get("toxic_ratio", 0.0))

danger_count = int(stats.get("danger_count", 0))
warning_count = int(stats.get("warning_count", 0))
normal_count = int(stats.get("normal_count", 0))

# st.markdown("### 📌 이번 주 전체 요약")
# st.markdown(f"**{week_summary}**")

left, _, right = st.columns([1, 0.2, 1.5])

# 1) 왼쪽: 워드클라우드 (지금은 keywords만 표시 / 추후 이미지로 교체)
with left:
    st.markdown("#### ☁️ 워드클라우드")
    keywords = wordcloud.get("keywords", []) or []
    if keywords:
        # st.caption("키워드(상위 일부)")
        # st.write(", ".join(keywords[:60]))

        draw_wordcloud(keywords)
    else:
        st.info("워드클라우드 키워드가 없습니다. (wordcloud.keywords)")
        

# 2) 오른쪽: 주요 지표 + 게이지
with right:
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("전체 글 수 (이번 주)", f"{total_posts}건")
    with c2:
        st.metric("위험 글 수", f"{danger_count}건")
    with c3:
        st.metric("부정 글 비율", f"{toxic_ratio * 100:.1f}%")
    st.caption("이번 주 속닥숲 리포트(stats) 기준")

    # 2) 위험/주의/보통 분포 게이지
    def draw_danger_gauge_level(total_posts, danger_count, warning_count, normal_count):
        if total_posts <= 0:
            st.info("이번 주에는 등록된 글이 없습니다.")
            return

        level_data = [
            {"level": "위험", "count": danger_count},
            {"level": "주의", "count": warning_count},
            {"level": "보통", "count": normal_count},
        ]

        level_color_map = {
            "위험": "#CE4A4A",  # 빨강
            "주의": "#E2AA3A",  # 노랑
            "보통": "#33955C",  # 초록
        }

        gauge_level = make_ratio_gauge(
            data=level_data,
            label_col="level",
            count_col="count",
            bar_label="위험/주의/보통 분포",
            color_map=level_color_map,
            font_size=15,
        )

        if gauge_level is not None:
            st.markdown("#### 🔎 위험 / 주의 / 보통 분포")
            st.altair_chart(gauge_level, use_container_width=True)
            st.caption("이번 주 전체 글 중 위험·주의·보통 비율(stats 기반)")
        else:
            st.info("게이지를 그릴 데이터가 없습니다.")

    draw_danger_gauge_level(total_posts, danger_count, warning_count, normal_count)

    # 3) 전체 글 대비 부정글 비율 게이지
    def draw_toxic_gauge(total_posts, neg_count, pos_count):
        if total_posts <= 0:
            st.info("이번 주에는 등록된 글이 없습니다.")
            return

        neg_data = [
            {"level": "부정글", "count": int(neg_count)},
            {"level": "일반글", "count": int(pos_count)},
        ]

        neg_color_map = {
            "부정글": "#CE4A4A",  # 빨강
            "일반글": "#9C9C9C",  # 회색
        }

        gauge_neg = make_ratio_gauge(
            data=neg_data,
            label_col="level",
            count_col="count",
            bar_label="전체 글 대비 부정글 비율",
            color_map=neg_color_map,
            font_size=15,
        )

        if gauge_neg is not None:
            st.markdown("#### 🧯 전체 글 대비 부정글 비율")
            st.altair_chart(gauge_neg, use_container_width=True)
            st.caption(f"전체 {total_posts}건 중 부정글 {neg_count}건(stats 기반)")
        else:
            st.info("게이지를 그릴 데이터가 없습니다.")

    draw_toxic_gauge(total_posts, toxic_posts, total_posts - toxic_posts)


# =========================================================
# 주요 이슈 Top 3 (key_topics 기반)
# =========================================================
if key_topics:
    st.markdown("#### 🔍 주요 이슈 Top 3")

    cols = st.columns(len(key_topics))
    for idx, topic in enumerate(key_topics):
        with cols[idx]:
            with st.container(border=True, height=350):
                st.markdown(f"##### **{topic.get('category', 'Unknown')}** **({topic.get('count', 0)}건)**")
                st.markdown(topic.get("summary", ""))

                st.markdown("###### 관련 원문 발췌:")
                for ex in (topic.get("excerpts", []) or [])[:3]:
                    st.markdown(f"  - {ex}")

                # 참조 post_ids 를 logs_df에서 필터링하여 표시
                # post_ids = topic.get("post_ids", []) or []
                # if post_ids:
                #     ref_posts = logs_df[logs_df["post_id"].isin(post_ids)].copy()
                #     ref_posts["created_at_sort"] = ref_posts["created_at"].fillna(pd.Timestamp.min)
                #     ref_posts = ref_posts.sort_values("created_at_sort", ascending=False)

                #     st.markdown("###### 관련 글 보기:")
                #     for _, r in ref_posts.iterrows():

                #         st.markdown(f"{r.get('clean_text','')}")
else:
    st.info("🔍 주요 이슈 Top 3 데이터가 없습니다.")

st.markdown("---")


# =========================================================
# 위험 글 하이라이트 (logs_df는 표시용)
# =========================================================
st.markdown("#### 🚨 위험 글 하이라이트")

risky_df = logs_df[
    (logs_df["severity"].isin(["high", "medium"])) | (logs_df["is_toxic"] == True)
].copy()

if risky_df.empty:
    st.info("이번 주에는 고위험/토식 글이 탐지되지 않았습니다.")
else:
    severity_rank = {"high": 0, "medium": 1, "low": 2}
    risky_df["severity_rank"] = risky_df["severity"].map(severity_rank).fillna(2)

    # created_at이 NaT면 정렬 꼬일 수 있어서 보정
    risky_df["created_at_sort"] = risky_df["created_at"].fillna(pd.Timestamp.min)

    risky_df = risky_df.sort_values(
        ["severity_rank", "is_toxic", "created_at_sort"],
        ascending=[True, False, False],
    )

    top_n = 3
    top_df = risky_df.head(top_n)
    rest_df = risky_df.iloc[top_n:]

    def render_risky_row(r):
        created_at = r["created_at"]
        created_str = created_at.strftime("%Y-%m-%d %H:%M") if pd.notna(created_at) else "-"

        if not r.get("summary"):
            header = f"Week {int(r.get('week', week_index))} / user {r.get('user_id', '-')}"
        else:
            header = (
                f"Week {int(r.get('week', week_index))} / user {r.get('user_id', '-')}"
                f"{created_str}\n\n **{r.get('summary','')}**"
            )

        if r.get("severity") == "high":
            st.error(header, icon="🔥")
        elif r.get("severity") == "medium":
            st.warning(header, icon="⚠️")
        else:
            st.info(header)

        st.markdown(f"{r.get('clean_text','')}")

    cols = st.columns(3)
    for idx, (_, row) in enumerate(top_df.iterrows()):
        with cols[idx % 3]:
            with st.container(border=True, height=200):
                render_risky_row(row)

    if not rest_df.empty:
        with st.expander(f"나머지 위험 글 {len(rest_df)}개 더 보기"):
            cols = st.columns(3)
            for idx, (_, row) in enumerate(rest_df.iterrows()):
                with cols[idx % 3]:
                    with st.container(border=True, height=200):
                        render_risky_row(row)

st.markdown("---")


# =========================================================
# 운영 개입 가이드 (ops_actions 기반)
# =========================================================
st.markdown("#### 🏃 운영 개입 가이드 (Top 3)")

if ops_actions:
    cols = st.columns(len(ops_actions))
    for idx, action in enumerate(ops_actions):
        with cols[idx]:
            with st.container(border=True, height=340):
                st.markdown(f"##### {action.get('title','')}")
                st.caption(f"action_type: **{action.get('action_type','-')}**")
                st.markdown(f"**대상**: {action.get('target','')}")
                st.markdown(f"**근거**: {action.get('reason','')}")
                st.markdown("**이번 주 실행 액션**")
                st.markdown(action.get("todo", ""))
else:
    st.info("이번 주 기준으로 제안할 액션이 없습니다.")

st.markdown("---")


# =========================================================
# (2) 📂 상세보기: 주제 분포(stats) + 드릴다운(원문은 logs_df)
# =========================================================
st.markdown("### 📂 상세보기")

# ---- stats에서 category_count / sub_category_count로 표/차트 구성 ----
category_count = stats.get("category_count", {}) or {}
sub_category_count = stats.get("sub_category_count", {}) or {}

cat_df = pd.DataFrame(
    [{"category": k, "count": v} for k, v in category_count.items()]
).sort_values("count", ascending=False)

# sub_category_count는 key 규격이 필요함: "category::sub_category" 권장
sub_rows = []
for key, cnt in sub_category_count.items():
    if isinstance(key, str) and "::" in key:
        cat, sub = key.split("::", 1)
    else:
        # 규격이 다르면 Unknown으로 몰아두되, key 자체를 sub로 보여줌
        cat, sub = "Unknown", str(key)
    sub_rows.append({"category": cat, "sub_category": sub, "count": cnt})

subcat_df = pd.DataFrame(sub_rows).sort_values("count", ascending=False)

if cat_df.empty:
    st.info("이번 주에는 등록된 주제가 없습니다. (stats.category_count 비어있음)")
else:
    left, _, right = st.columns([1, 0.2, 1.5])

    # -----------------------------
    # 왼쪽: 가로 막대 그래프 (카테고리별 글 수)
    # -----------------------------
    with left:
        st.markdown("#### 🔎 주제별 글 수")

        topic_chart = (
            alt.Chart(cat_df)
            .mark_bar()
            .encode(
                y=alt.Y("category:N", title="카테고리", sort="-x"),
                x=alt.X("count:Q", title="글 수"),
                tooltip=["category", "count"],
            )
            .properties(height=200)
        )
        st.altair_chart(topic_chart, use_container_width=True)
        st.caption("이번 주 속닥숲에 올라온 글을 주제별로 집계한 그래프입니다. (stats 기반)")

        st.markdown("#### 주제별 세부 이슈 리스트")

        if subcat_df.empty:
            st.info("이번 주에는 집계할 세부 이슈가 없습니다. (stats.sub_category_count 비어있음)")
        else:
            category_summary_df = (
                subcat_df.groupby("category")
                .apply(
                    lambda g: [
                        f"{row['sub_category']} ({row['count']}건)"
                        for _, row in g.iterrows()
                    ]
                )
                .reset_index(name="세부 이슈")
                .rename(columns={"category": "카테고리"})
            )

            st.dataframe(
                category_summary_df,
                hide_index=True,
                use_container_width=True,
            )

    # st.dataframe(
    #             logs_df,
    #             hide_index=True,
    #             use_container_width=True,
    #         )
    # -----------------------------
    # 오른쪽: 드릴다운 (원문은 logs_df에서 필터링)
    # -----------------------------
    with right:
        st.markdown("#### 📌 주제 + 세부 이슈별 글 보기")

        categories = cat_df["category"].tolist()
        selected_category = st.selectbox("주제 선택", categories)
        

        # 선택 카테고리의 세부 이슈 목록은 stats 기반(subcat_df) 우선
        sub_options = subcat_df[subcat_df["category"] == selected_category]["sub_category"].tolist()

        # stats에 sub가 없으면 logs에서 fallback
        if not sub_options:
            sub_options = (
                logs_df[logs_df["category"] == selected_category]["sub_category"]
                .dropna()
                .astype(str)
                .unique()
                .tolist()
            )

        if not sub_options:
            st.info("해당 주제에 세부 이슈가 없습니다.")
        else:
            selected_sub = st.selectbox("세부 이슈 선택", sub_options)

            filtered_posts = logs_df[
                (logs_df["category"] == selected_category)
                & (logs_df["sub_category"].astype(str) == str(selected_sub))
            ].copy()

            filtered_posts["created_at_sort"] = filtered_posts["created_at"].fillna(pd.Timestamp.min)
            filtered_posts = filtered_posts.sort_values("created_at_sort", ascending=False)

            def render_row(r):
                created_at = r["created_at"]
                created_str = created_at.strftime("%Y-%m-%d %H:%M") if pd.notna(created_at) else "-"

                # summary가 있는 경우만
                if not r.get("summary"):
                    header = f"Week {int(r.get('week', week_index))} / user {r.get('user_id', '-')}" 
                else:   
                    header = (
                        f"Week {int(r.get('week', week_index))} / user {r.get('user_id', '-')}"
                        f" / {created_str}\n\n **{r.get('summary','')}**"
                    )

                if r.get("severity") == "high":
                    st.error(header, icon="🔥")
                elif r.get("severity") == "medium":
                    st.warning(header, icon="⚠️")
                else:
                    st.info(header)
                
                st.markdown(f"{r.get('clean_text','')}")

            if filtered_posts.empty:
                st.info("해당 주제/세부 이슈에 해당하는 글이 없습니다.")
            else:
                st.caption(
                    f"선택한 주제: **{selected_category}** / 세부 이슈: **{selected_sub}** "
                    f"(총 {len(filtered_posts)}건)"
                )

                for _, row in filtered_posts.iterrows():
                    with st.container(border=True):
                        render_row(row)
