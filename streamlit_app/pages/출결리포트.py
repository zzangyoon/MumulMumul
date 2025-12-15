# streamlit_app/attendance_report.py

import streamlit as st
import pandas as pd
import altair as alt
from datetime import date, datetime

from api.attendance import (
    get_attendance_report,       # GET /attendance/report
    generate_attendance_report,  # POST /attendance/report/generate
)

from api.camp import fetch_camps

# ============================================
# 0. 페이지 기본 설정
# ============================================
st.set_page_config(
    page_title="출결 관리",
    page_icon="👥",
    layout="wide"
)

st.title("🔥 출결 리포트")

# ============================================
# 0-1. 세션 기반 데이터 캐시 설정
# ============================================
if "attendance_session" not in st.session_state:  # 한 번만 초기화
    st.session_state["attendance_session"] = {
        "camps": None,                 # fetch_camps() 결과
        "camp_info": None,             # {name: camp_dict}
        "attendance_reports": {},      # {f"{camp_id}_{date_str}": payload}
    }

session_cache = st.session_state["attendance_session"]

# --- 캠프 목록은 세션에 한 번만 저장 ---
if session_cache["camps"] is None:
    res = fetch_camps()  # [{camp_id, name, start_date, end_date, ...}, ...] 가정
    camps = res.get("camps", [])
    camp_info = {c["name"]: c for c in camps}
    session_cache["camps"] = camps
    session_cache["camp_info"] = camp_info
else:
    camps = session_cache["camps"]
    camp_info = session_cache["camp_info"]

# ============================================
# 1. 사이드바 필터 (캠프 / 날짜)
# ============================================
st.sidebar.header("필터 설정")

camp_name = st.sidebar.selectbox("반 선택", list(camp_info.keys()))
camp = camp_info[camp_name]
camp_id = camp["camp_id"]

# camp_start_date, camp_end_date는 문자열이라고 가정 ("YYYY-MM-DD")
camp_start_date = datetime.strptime(camp["start_date"], "%Y-%m-%d")
camp_end_date = datetime.strptime(camp["end_date"], "%Y-%m-%d")

selected_date: datetime = st.sidebar.date_input(
    "기준 날짜 선택",
    value=camp_start_date,       # 기본값: 캠프 시작일
    min_value=camp_start_date,   # 최소: 캠프 시작
    max_value=camp_end_date,     # 최대: 캠프 종료
)

# 캐시 키: 캠프 + 날짜
date_key = selected_date
report_key = f"{camp_id}_{date_key}"
reports_cache = session_cache["attendance_reports"]

# 1) 세션 캐시에서 먼저 찾기
payload = reports_cache.get(report_key)

# 2) 세션에 없으면 → 백엔드에서 조회 (이미 생성된 리포트가 있으면 캐시)
if payload is None:
    db_report = get_attendance_report(
        camp_id=camp_id,
        target_date=date_key,  # 클라이언트 래퍼에서 쿼리 파라미터로 전달
    )
    if db_report is not None:
        payload = db_report
        reports_cache[report_key] = payload
    else:
        payload = None

# 리포트 재생성 버튼 (강제 새로 생성)
generate_clicked = st.sidebar.button("리포트 생성하기")
if generate_clicked:
    with st.spinner("리포트 생성 중입니다..."):
        # POST로 새 리포트 생성 후 응답 payload 받기
        payload = generate_attendance_report(
            camp_id=camp_id,
            target_date=date_key,
        )
        session_cache["attendance_reports"][report_key] = payload

# 최종 payload 다시 읽기
payload = session_cache["attendance_reports"].get(report_key)

# ============================================
# 2. payload 유효성 체크
# ============================================
if not payload:
    st.info(
        "아직 해당 캠프/날짜의 출결 리포트가 없습니다.\n"
        "왼쪽에서 '리포트 생성하기' 버튼을 눌러 리포트를 생성해 주세요."
    )
    st.stop()


summary = payload.get("summary", {}) or {}
students_raw = payload.get("students", []) or []

if not students_raw:
    st.warning("학생별 출결 데이터가 없습니다.")
    st.stop()

df = pd.DataFrame(students_raw)

# 안전한 기본값 처리
if "risk_level" not in df.columns:
    df["risk_level"] = "정상"
if "pattern_type" not in df.columns:
    df["pattern_type"] = ""
if "ops_action" not in df.columns:
    df["ops_action"] = ""

# ============================================
# 3. 페이지 타이틀 및 요약
# ============================================
st.subheader(f"{camp_name} / {selected_date.strftime('%Y-%m-%d')} 기준 출결 리포트")

# ============================================
# 3-1. 상단 KPI 요약 영역
# ============================================
attendance_rate = summary.get(
    "attendance_rate",
    df["attendance_rate"].mean() if "attendance_rate" in df.columns else None,
)
high_risk_count = summary.get(
    "high_risk_count",
    int((df["risk_level"] == "고위험").sum()),
)
warning_count = summary.get(
    "warning_count",
    int(df["risk_level"].isin(["위험", "주의"]).sum()),
)
total_students = summary.get("total_students", len(df))

col1, col2, col3, col4 = st.columns(4)

with col1:
    if attendance_rate is not None:
        st.metric("전체 출석률 (누적)", f"{attendance_rate*100:.1f}%")
    else:
        st.metric("전체 출석률 (누적)", "-")

with col2:
    st.metric("고위험자 수", f"{high_risk_count}명")

with col3:
    st.metric("주의 대상 수", f"{warning_count}명")

with col4:
    st.metric("전체 인원", f"{total_students}명")

st.markdown("---")

# ============================================
# 4. 고위험 학생 카드 3개 (Critical Area)
# ============================================

def risk_to_color(risk: str) -> str:
    if risk == "고위험":
        return "#ffcccc"
    if risk == "위험":
        return "#ffe4b5"
    if risk == "주의":
        return "#fff7cc"
    return "#f5f5f5"

def risk_to_badge(risk: str) -> str:
    if risk == "고위험":
        return "🔥 고위험"
    if risk == "위험":
        return "⚠️ 위험"
    if risk == "주의":
        return "👀 주의"
    return "✅ 정상"

st.markdown("### 🚨 고위험 학생")

high_risk_df = df[df["risk_level"] == "고위험"].copy()

if high_risk_df.empty:
    st.info(
        "고위험으로 분류된 학생이 없습니다.\n"
        "그래도 출석 패턴이 떨어지는 학생이 있는지 아래 상세 테이블에서 확인해 주세요."
    )
else:
    # 출석률 오름차순(낮은 순) + 결석 많은 순으로 정렬
    sort_cols = []
    ascending = []
    if "attendance_rate" in high_risk_df.columns:
        sort_cols.append("attendance_rate")
        ascending.append(True)
    if "absent_count" in high_risk_df.columns:
        sort_cols.append("absent_count")
        ascending.append(False)

    if sort_cols:
        high_risk_df = high_risk_df.sort_values(
            by=sort_cols,
            ascending=ascending,
        )

    top3 = high_risk_df.head(3)
    cols = st.columns(len(top3))

    for idx, (_, row) in enumerate(top3.iterrows()):
        with cols[idx]:
            name = row.get("name", f"학생 {row.get('student_id', '')}")
            pattern = row.get("pattern_type", "")
            att_rate = row.get("attendance_rate", None)
            absent = row.get("absent_count", 0)
            late = row.get("late_count", 0)
            trend = row.get("trend", None)

            # --- st.error 카드 본문 구성 ---
            stats_line = []
            if att_rate is not None:
                stats_line.append(f"출석률 {att_rate*100:.1f}%")
            if absent is not None:
                stats_line.append(f"결석 {int(absent)}회")
            if late is not None:
                stats_line.append(f"지각 {int(late)}회")

            lines = [
                f"**{name}**  |  {risk_to_badge(row.get('risk_level', ''))}",
            ]
            if pattern:
                lines.append(f"- 패턴: {pattern}")
            if stats_line:
                lines.append(f"- " + " · ".join(stats_line))

            if trend is not None:
                arrow = "⬇️" if trend < 0 else "⬆️"
                lines.append(f"- 최근 변화: {arrow} {trend*100:.1f}%p")

            # 🔴 고위험 학생 카드는 st.error로 강조
            st.error("\n".join(lines))

            st.markdown("**권장 즉시 조치**")
            st.markdown(
                "- 1:1 체크인 메시지 발송  \n"
                "- 금일 데일리 미팅에서 상태 확인  \n"
                "- 필요 시 팀 담당자와 연계"
            )

    # 나머지 고위험 학생은 토글로 숨기기
    if len(high_risk_df) > 3:
        with st.expander(f"나머지 고위험 학생 {len(high_risk_df) - 3}명 더 보기"):
            st.dataframe(
                high_risk_df,
                hide_index=True,
                use_container_width=True,
            )

st.markdown("---")

# ============================================
# 5. 운영진 우선 액션 Top 3
# ============================================

st.markdown("### 🏃 운영진 우선 액션 Top 3")

def build_ops_actions_for_attendance(df: pd.DataFrame):
    actions = []

    # 1) 고위험자 있으면: 1:1 케어
    high_risk_df = df[df["risk_level"] == "고위험"]
    if not high_risk_df.empty:
        names = ", ".join(high_risk_df["name"].astype(str).head(3).tolist())
        actions.append(
            {
                "title": "1. 고위험 학생 1:1 체크인",
                "target": f"고위험 학생: {names} ...",
                "reason": f"고위험으로 분류된 학생이 총 {len(high_risk_df)}명입니다.",
                "todo": (
                    "각 학생에게 개별적으로 현재 상황을 묻는 체크인 메시지를 보내고, "
                    "필요 시 15~20분 정도의 간단한 1:1 상담 시간을 제안합니다."
                ),
            }
        )

    # 2) 위험/주의 학생이 많으면: 그룹 케어
    warn_df = df[df["risk_level"].isin(["위험", "주의"])]
    if not warn_df.empty:
        actions.append(
            {
                "title": "2. 주의/위험 학생 그룹 케어 세션",
                "target": "주의/위험 등급 학생 전체",
                "reason": f"주의/위험 등급 학생이 총 {len(warn_df)}명입니다.",
                "todo": (
                    "공통된 어려움이 있는지 파악하기 위해 3~5명 단위 그룹으로 짧은 케어 세션을 진행하고, "
                    "진도/과제 난이도/시간 관리 측면에서 지원이 필요한 부분을 함께 정리합니다."
                ),
            }
        )

    # 3) 전체 출석률이 낮으면: 공지/환경 개선
    avg_att = df["attendance_rate"].mean() if "attendance_rate" in df.columns else None
    if avg_att is not None and avg_att < 0.8:
        actions.append(
            {
                "title": "3. 전체 출석률 저하 공지 및 참여 동기 재강조",
                "target": "전체 수강생",
                "reason": f"누적 평균 출석률이 {avg_att*100:.1f}%로 낮은 편입니다.",
                "todo": (
                    "현재 출석 현황을 간단히 공유하고, 출석이 학습성과와 어떤 관련이 있는지 안내합니다. "
                    "또한 매일 시작 5분 전 리마인드 공지를 보내 출석률을 끌어올립니다."
                ),
            }
        )

    return actions[:3]

ops_actions = build_ops_actions_for_attendance(df)

if ops_actions:
    cols = st.columns(len(ops_actions))
    for idx, action in enumerate(ops_actions):
        with cols[idx]:
            with st.container(border=True):
                st.markdown(f"#### {action['title']}")
                st.markdown(f"- **대상**: {action['target']}")
                st.markdown(f"- **근거**: {action['reason']}")
                st.markdown("**이번 기준일까지 실행하면 좋은 액션**")
                st.markdown(action["todo"])
else:
    st.info("현재 데이터 기준으로 별도의 우선 액션 제안은 없습니다.")

st.markdown("---")

# ============================================
# 6. 출결 상세 테이블 (운영진 조치 칼럼 포함)
# ============================================

st.markdown("### 📂 출결 상세 테이블 (누적)")

columns_map = {
    "name": "이름",
    "attendance_rate": "출석률",
    "absent_count": "결석",
    "late_count": "지각",
    "early_leave_count": "조퇴",
    "pattern_type": "출결 패턴",
    "risk_level": "위험 등급",
    "trend": "최근 변화율",
    "ops_action": "운영진 조치",
}
show_cols = [c for c in columns_map.keys() if c in df.columns]

display_df = df[show_cols].rename(columns=columns_map)

# 퍼센트/소수 처리
if "출석률" in display_df.columns:
    display_df["출석률"] = (display_df["출석률"] * 100).round(1)

if "최근 변화율" in display_df.columns:
    display_df["최근 변화율"] = pd.to_numeric(display_df["최근 변화율"], errors="coerce")
    display_df["최근 변화율"] = (display_df["최근 변화율"] * 100).round(1)


edited_df = st.data_editor(
    display_df,
    hide_index=True,
    use_container_width=True,
    num_rows="fixed",
    column_config={
        "위험 등급": st.column_config.SelectboxColumn(
            "위험 등급",
            options=["고위험", "위험", "주의", "정상"],
        ),
        "운영진 조치": st.column_config.TextColumn(
            "운영진 조치",
            help="해당 학생에 대해 어떤 조치를 했는지 간단히 기록하세요.",
        ),
    },
)