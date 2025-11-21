import streamlit as st
import pandas as pd
import altair as alt
from datetime import datetime, timedelta

st.set_page_config(layout="wide")
st.title("💬 익명 게시판 인사이트")

# -----------------------------
# 가짜 데이터 생성
# -----------------------------
today = datetime.now().date()
dates = [today - timedelta(days=i) for i in range(13, -1, -1)]
posts_per_day = [8, 9, 10, 11, 12, 10, 9, 13, 14, 16, 15, 18, 20, 21]

df_daily = pd.DataFrame(
    {"날짜": dates, "게시글 수": posts_per_day}
)

category_data = pd.DataFrame(
    {"카테고리": ["고민", "건의", "기타"], "게시글 수": [34, 16, 4]}
)

sentiment_data = pd.DataFrame(
    {"감정": ["positive", "neutral", "negative"], "게시글 수": [12, 28, 14]}
)

keywords_df = pd.DataFrame(
    {
        "키워드": ["git_conflict", "일정압박", "반 분위기", "리더상담"],
        "언급 횟수": [19, 14, 11, 7],
    }
)

# -----------------------------
# 탭 구성
# -----------------------------
tab_summary, tab_ai, tab_detail = st.tabs(
    ["요약", "AI 심층 분석", "지표 상세 보기"]
)

# -----------------------------
# 탭 1: 요약
# -----------------------------
with tab_summary:
    st.subheader("이번 주 핵심 요약")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("이번 주 익명 게시글 수", "86건", "▲ 12건")
    with col2:
        st.metric("고민 글 비율", "63%", "▲ 15%p")
    with col3:
        st.metric("Negative 감정 비율", "31%", "▲ 9%p")

    st.markdown("### 🔍 이번 주 익명 게시판 핵심 이슈")
    st.info(
        """
        이번 주에는 **Git 협업**과 **프로젝트 일정 압박** 관련 고민이 크게 증가했습니다.  
        - git_conflict, 브랜치 꼬임, merge 에러  
        - 일정이 빠르다는 표현, 시간 부족  
        - 반 분위기, 말 꺼내기 어려움  
        등이 자주 언급되고 있습니다.
        """
    )

    st.markdown("---")
    st.markdown("### 게시글 흐름 및 분위기 한눈에 보기")

    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("**1) 일별 익명 게시글 수 추이**")
        chart_daily = (
            alt.Chart(df_daily)
            .mark_line(point=True)
            .encode(
                x=alt.X("날짜:T", title="날짜"),
                y=alt.Y("게시글 수:Q", title="게시글 수"),
                tooltip=["날짜", "게시글 수"],
            )
            .properties(height=260)
        )
        st.altair_chart(chart_daily, use_container_width=True)
        st.caption("최근 2주 동안 익명 게시글이 얼마나 올라왔는지 보여줍니다.")

    with col_b:
        st.markdown("**2) 카테고리별 게시글 분포 (최근 7일)**")
        chart_cat = (
            alt.Chart(category_data)
            .mark_bar()
            .encode(
                x=alt.X("게시글 수:Q", title="게시글 수"),
                y=alt.Y("카테고리:N", sort="-x", title="카테고리"),
                color=alt.Color("카테고리:N", legend=None),
                tooltip=["카테고리", "게시글 수"],
            )
            .properties(height=260)
        )
        st.altair_chart(chart_cat, use_container_width=True)
        st.caption("고민/건의/기타 중 어떤 유형의 글이 많은지 확인할 수 있습니다.")

# -----------------------------
# 탭 2: AI 심층 분석
# -----------------------------
with tab_ai:
    st.subheader("AI 요약 인사이트")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.info(
            "**분위기 변화**\n\n"
            "- 고민 글 비율: 48% → 63%\n"
            "- Negative 감정 비율: 22% → 31%"
        )
    with col2:
        st.warning(
            "**주요 스트레스 요인**\n\n"
            "- 촉박하게 느껴지는 일정\n"
            "- 말 꺼내기 어려운 반 분위기"
        )
    with col3:
        st.success(
            "**운영 관점 시사점**\n\n"
            "- Git/일정 구간에 추가 지원 필요\n"
            "- 일부 반에 심리적 부담 완화 케어 필요"
        )

    st.markdown("---")

    st.markdown("### 1. 주요 이슈 요약")

    st.markdown(
        """
- `git_conflict`, `브랜치 꼬임`, `merge 에러` 등 **Git 관련 키워드**가 지난주 대비 크게 증가했습니다.  
- “시간이 부족하다”, “일정이 너무 빠르다” 등 **일정 압박**을 나타내는 문장이 자주 등장합니다.  
- 일부 반에서는 “뒤처지는 느낌”, “말 꺼내기 어렵다”와 같은 **심리적 부담 표현**이 반복됩니다.
"""
    )

    with st.expander("지표 기반 근거 보기"):
        st.markdown(
            """
- Git 관련 키워드 언급: 7건 → **19건**  
- '일정', '시간 부족' 관련 표현: 5건 → **13건**  
- 고민 글 비율: 48% → **63%**  
- negative 감정 게시글: 9건 → **14건**  

예시 문장:

- “git conflict 때문에 하루 종일 붙잡고 있어요. 반 친구들한테 미안하네요.”
- “진도가 빠르게 지나가서 복습할 시간이 부족합니다.”
- “자꾸만 뒤처지는 느낌이라 말 꺼내기가 어렵네요.”
"""
        )

    st.markdown("### 2. 운영 액션 제안")

    st.markdown(
        """
- **Git 관련 부담 완화**
  - Git conflict 해결 실습 세션 1회 추가  
  - 자주 발생하는 오류 유형을 정리한 “문제 유형별 해결 가이드” 제공
- **일정 압박 조정**
  - 이번 주 과제 마감일 1일 유예, 선택 과제 일부 제외 검토  
  - “지금 구간이 누구에게나 어려운 구간”이라는 메시지 함께 전달
- **반 단위 케어**
  - 고민 글이 많이 올라온 반 중심으로 짧은 체크인 미팅 제안  
  - 반 리더와 함께 분위기·소통 구조 점검
"""
    )

# -----------------------------
# 탭 3: 지표 상세 보기
# -----------------------------
with tab_detail:
    st.subheader("지표 탐색")

    st.markdown(
        """
아래에서 보고 싶은 지표 유형을 선택하고,  
각 지표가 **무엇을 의미하는지 설명**과 함께 확인할 수 있습니다.
"""
    )

    subtab1, subtab2, subtab3, subtab4 = st.tabs(
        [
            "게시글 추이",
            "감정/카테고리 분포",
            "키워드",
            "표 형식으로 보기",
        ]
    )

    # 1) 게시글 추이
    with subtab1:
        st.markdown("#### 일별 익명 게시글 수 추이")
        st.markdown(
            """
- 특정 날에 게시글이 몰렸다면, 그날 어떤 공지/수업/이벤트가 있었는지 함께 보는 것이 좋습니다.  
- 갑작스러운 증가 구간은 “운영 이슈 또는 커리큘럼 이슈” 가능성이 있습니다.
"""
        )
        chart_daily_detail = (
            alt.Chart(df_daily)
            .mark_line(point=True)
            .encode(
                x=alt.X("날짜:T", title="날짜"),
                y=alt.Y("게시글 수:Q", title="게시글 수"),
                tooltip=["날짜", "게시글 수"],
            )
            .properties(height=320)
        )
        st.altair_chart(chart_daily_detail, use_container_width=True)

    # 2) 감정/카테고리 분포
    with subtab2:
        st.markdown("#### 감정 및 카테고리 분포")

        col_x1, col_x2 = st.columns(2)

        with col_x1:
            st.markdown("**1) 감정 분포 (최근 7일)**")
            chart_sent = (
                alt.Chart(sentiment_data)
                .mark_bar()
                .encode(
                    x=alt.X("게시글 수:Q", title="게시글 수"),
                    y=alt.Y("감정:N", sort="-x", title="감정"),
                    color=alt.Color("감정:N", legend=None),
                    tooltip=["감정", "게시글 수"],
                )
                .properties(height=280)
            )
            st.altair_chart(chart_sent, use_container_width=True)

        with col_x2:
            st.markdown("**2) 카테고리 분포 (최근 7일)**")
            chart_cat_detail = (
                alt.Chart(category_data)
                .mark_bar()
                .encode(
                    x=alt.X("게시글 수:Q", title="게시글 수"),
                    y=alt.Y("카테고리:N", sort="-x", title="카테고리"),
                    color=alt.Color("카테고리:N", legend=None),
                    tooltip=["카테고리", "게시글 수"],
                )
                .properties(height=280)
            )
            st.altair_chart(chart_cat_detail, use_container_width=True)

    # 3) 키워드
    with subtab3:
        st.markdown("#### 상위 키워드")

        st.markdown(
            """
- 익명 게시판에서 자주 등장하는 단어를 통해  
  **학습자들이 어디에 집중하고 있는지, 무엇에 스트레스를 받는지** 파악할 수 있습니다.
"""
        )
        chart_keywords = (
            alt.Chart(keywords_df)
            .mark_bar()
            .encode(
                x=alt.X("언급 횟수:Q", title="언급 횟수"),
                y=alt.Y("키워드:N", sort="-x", title="키워드"),
                color=alt.Color("키워드:N", legend=None),
                tooltip=["키워드", "언급 횟수"],
            )
            .properties(height=300)
        )
        st.altair_chart(chart_keywords, use_container_width=True)

    # 4) 표 형식
    with subtab4:
        st.markdown("#### 원본 수치 보기")

        st.markdown("**카테고리별 게시글 수 (최근 7일)**")
        st.dataframe(category_data, use_container_width=True)

        st.markdown("**감정 분포 (최근 7일)**")
        st.dataframe(sentiment_data, use_container_width=True)

        st.markdown("**상위 키워드**")
        st.dataframe(keywords_df, use_container_width=True)
