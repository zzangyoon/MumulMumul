import streamlit as st
import pandas as pd
import altair as alt

st.set_page_config(layout="wide")
st.title("🧍 출결 & 이탈 위험 모니터링")

# -----------------------------
# 가짜 데이터 생성
# -----------------------------
weeks = ["Week 1", "Week 2", "Week 3", "Week 4", "Week 5", "Week 6"]
attendance_rate = [88, 86, 84, 83, 80, 82]

df_attendance = pd.DataFrame(
    {"주차": weeks, "출석률": attendance_rate}
)

classes = ["1반", "2반", "3반", "4반"]
class_attendance = [86, 79, 81, 83]
df_class = pd.DataFrame(
    {"반": classes, "출석률": class_attendance}
)

df_users = pd.DataFrame(
    {
        "이름": ["김지훈", "이서연", "박민수", "최유진", "정우성"],
        "반": ["1반", "2반", "2반", "3반", "4반"],
        "최근 7일 접속일수": [6, 2, 7, 3, 5],
        "최근 7일 접속시간(분)": [540, 80, 610, 150, 320],
        "최근 7일 회의 참석 횟수": [5, 0, 4, 1, 3],
        "최근 7일 캠프 체류시간(분)": [220, 0, 180, 40, 130],
        "최근 7일 챗봇 질문 수": [9, 1, 12, 3, 2],
        "리스크 상태": ["정상", "고위험", "정상", "주의", "주의"],
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
        st.metric("전체 평균 출석률", "82%", "-3%p")
    with col2:
        st.metric("3일 이상 연속 미접속", "5명")
    with col3:
        st.metric("고위험 학습자", "3명")

    st.markdown("### 🔍 이번 주 출결·이탈 위험 요약")
    st.info(
        """
        전체 출석률은 큰 폭의 변동 없이 유지되지만,  
        **초반에는 활발히 참여했다가 최근 1주일 간 활동이 급감한 학습자**가 몇 명 포착됩니다.  
        일부 반에서는 형식적 출석만 유지되고 실제 상호작용은 거의 없는 패턴도 보입니다.
        """
    )

    st.markdown("---")
    st.markdown("### 출석 및 반별 현황 한눈에 보기")

    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("**1) 주차별 전체 출석률 추이**")
        chart_att = (
            alt.Chart(df_attendance)
            .mark_line(point=True)
            .encode(
                x=alt.X("주차:N", title="주차"),
                y=alt.Y("출석률:Q", title="출석률(%)"),
                tooltip=["주차", "출석률"],
            )
            .properties(height=260)
        )
        st.altair_chart(chart_att, use_container_width=True)
        st.caption("주차별 평균 출석률 흐름입니다.")

    with col_b:
        st.markdown("**2) 반별 평균 출석률**")
        chart_class = (
            alt.Chart(df_class)
            .mark_bar()
            .encode(
                x=alt.X("출석률:Q", title="출석률(%)"),
                y=alt.Y("반:N", sort="-x", title="반"),
                color=alt.Color("반:N", legend=None),
                tooltip=["반", "출석률"],
            )
            .properties(height=260)
        )
        st.altair_chart(chart_class, use_container_width=True)
        st.caption("어떤 반이 상대적으로 출석률이 낮은지 한눈에 볼 수 있습니다.")

# -----------------------------
# 탭 2: AI 심층 분석
# -----------------------------
with tab_ai:
    st.subheader("AI 요약 인사이트")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.info(
        "**이탈 위험 패턴**\n\n"
        "- 초반 고활동 → 최근 급감 유형 존재\n"
        "- 형식적 출석(접속만 유지, 참여 적음) 패턴 일부 반에서 관찰"
    )
    with col2:
        st.warning(
        "**반 단위 문제 신호**\n\n"
        "- 2반: 출석률·참여 모두 낮은 편\n"
        "- 3반: 출석률은 유지되지만 소수 인원 중심 참여 구조"
      )
    with col3:
        st.success(
        "**우선 개입 대상**\n\n"
        "- 최근 7일간 접속·회의·캠프 체류가 급감한 학습자\n"
        "- 출석률이 낮고 발언 편차가 큰 반"
      )  
    
    st.markdown("---")

    st.markdown("### 1. 이탈 위험 패턴 요약")

    st.markdown(
        """
- **초반 고활동 → 최근 급감 유형**
  - 예: `이서연(2반)`, `최유진(3반)`  
  - Week 1~2에는 출석·회의·캠프 참여가 활발했으나, 최근 7일간 접속일수와 참여도가 모두 크게 감소했습니다.
- **형식적 출석 유형**
  - 접속은 유지하지만, 회의/캠프/질문이 거의 없는 학습자가 일부 존재합니다.
  - 특히 **2반**에서 이 패턴이 두드러지며, 반 분위기 및 소속감 저하와 연결될 수 있습니다.
"""
    )

    with st.expander("지표 기반 근거 보기"):
        st.markdown(
            """
- 이서연(2반)
  - Week 1~2:
    - 주 6일 접속, 총 접속시간 480분 이상  
    - 회의 참석 4회, 캠프 체류 160분  
  - 최근 7일:
    - 접속일수 2일, 총 접속시간 80분  
    - 회의·캠프 참여 0회  

- 2반
  - 반 평균 출석률: **79%** (전체 평균 82% 대비 낮음)  
  - 캠프 체류시간과 회의 참석률 모두 다른 반 대비 낮은 수준  

- 3반
  - 출석률: 81%로 평균 수준  
  - 회의·캠프에서 실제 발언/참여는 소수 인원에 집중
"""
        )

    st.markdown("### 2. 운영 액션 제안")

    st.markdown(
        """
- **고위험 학습자 개별 케어**
  - 최근 활동이 급감한 학습자에게는 **안부와 부담 완화에 초점을 둔 1:1 메시지**를 보내는 것이 좋습니다.
- **반 단위 개입**
  - 2반: 반 리더와 협의 후, 모든 인원이 한 번씩 말하는 구조 도입(라운드형 공유)  
  - 3반: 특정 인원에게만 업무가 쏠리지 않도록 역할 재배분 논의
- **캠프 전체 메시지**
  - 출석 리듬이 잠시 흔들리는 시기가 있을 수 있음을 인정해주고,  
    “이번 주는 3일만 정해진 시간에 접속하기” 같은 **작은 목표**를 제안
"""
    )

# -----------------------------
# 탭 3: 지표 상세 보기
# -----------------------------
with tab_detail:
    st.subheader("지표 탐색")

    st.markdown(
        """
출결과 참여 데이터를 여러 관점에서 나누어 보고,  
어떤 반·어떤 패턴에 먼저 개입해야 할지 판단할 수 있습니다.
"""
    )

    subtab1, subtab2, subtab3, subtab4 = st.tabs(
        [
            "주차별 출석률",
            "반별 출석률",
            "학습자별 참여 패턴",
            "표 형식으로 보기",
        ]
    )

    # 1) 주차별 출석률
    with subtab1:
        st.markdown("#### 주차별 전체 출석률 추이")

        st.markdown(
            """
- 특정 주차 이후 출석률이 눈에 띄게 떨어진다면,  
  그 구간의 커리큘럼 난이도/운영 이슈와 함께 보는 것이 좋습니다.
"""
        )

        chart_att_detail = (
            alt.Chart(df_attendance)
            .mark_line(point=True)
            .encode(
                x=alt.X("주차:N", title="주차"),
                y=alt.Y("출석률:Q", title="출석률(%)"),
                tooltip=["주차", "출석률"],
            )
            .properties(height=320)
        )
        st.altair_chart(chart_att_detail, use_container_width=True)

    # 2) 반별 출석률
    with subtab2:
        st.markdown("#### 반별 평균 출석률 비교")

        st.markdown(
            """
- 반별 출석률은 “어디부터 먼저 살펴봐야 할지”를 알려주는 지표입니다.  
- 출석률이 낮은 반은 “분위기, 난이도, 일정” 등 추가적인 점검이 필요합니다.
"""
        )

        chart_class_detail = (
            alt.Chart(df_class)
            .mark_bar()
            .encode(
                x=alt.X("출석률:Q", title="출석률(%)"),
                y=alt.Y("반:N", sort="-x", title="반"),
                color=alt.Color("반:N", legend=None),
                tooltip=["반", "출석률"],
            )
            .properties(height=320)
        )
        st.altair_chart(chart_class_detail, use_container_width=True)

    # 3) 학습자별 참여 패턴
    with subtab3:
        st.markdown("#### 학습자별 최근 7일 참여 현황 예시")

        st.markdown(
            """
- **3일 이상 미접속 + 회의/캠프 참여 0회** 학습자는 우선 순위로 케어할 필요가 있습니다.  
- 접속은 유지하지만 상호작용이 거의 없는 학습자도 “조용한 이탈 위험”으로 볼 수 있습니다.
"""
        )

        st.dataframe(df_users, use_container_width=True)

    # 4) 표 형식
    with subtab4:
        st.markdown("#### 원본 수치 보기")

        st.markdown("**주차별 전체 출석률**")
        st.dataframe(df_attendance, use_container_width=True)

        st.markdown("**반별 평균 출석률**")
        st.dataframe(df_class, use_container_width=True)

        st.markdown("**학습자별 참여 현황 예시**")
        st.dataframe(df_users, use_container_width=True)
