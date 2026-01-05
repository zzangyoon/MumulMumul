# streamlit_app/attendance_report.py

import streamlit as st
import pandas as pd
import altair as alt
from datetime import date, datetime

from api.attendance import (
    get_attendance_report,       # GET /attendance/report
    generate_attendance_report,
    get_attendance_ruleset,
    save_attendance_ruleset,  # POST /attendance/report/generate
)

from api.camp import fetch_camps
from streamlit_app.container.chart import make_ratio_gauge
from streamlit_app.container.chatbot import display_chatbot
from streamlit_app.session import get_camp_session

# ============================================
# 0. 페이지 기본 설정
# ============================================
st.set_page_config(
    page_title="출결 리포트",
    page_icon="👥",
    layout="wide"
)

# ============================================
# 0-1. 세션 기반 데이터 캐시 설정
# ============================================
camp_session_cache = get_camp_session()

if "attendance_session" not in st.session_state:  # 한 번만 초기화
    st.session_state["attendance_session"] = {
        "attendance_reports": {},      # {f"{camp_id}_{date_str}": payload}
        "attendance_rulesets": {},         # {camp_id: ruleset_payload}
        "attendance_ruleset_raw": {},      # {camp_id: raw_rules_text} (클라 보관용)
    }

session_cache = st.session_state["attendance_session"]
camp_session_cache = st.session_state["camp_session"]
camps = camp_session_cache["camps"]
camp_name_to_id = camp_session_cache["camp_name_to_id"]

# ============================================
# 1. 사이드바 필터 (캠프 / 날짜)
# ============================================
st.sidebar.header("필터 설정")

camp_name_list = [camp["name"] for camp in camps.values()]
camp_name = st.sidebar.selectbox("반 선택", camp_name_list)
camp_index = camp_name_to_id[camp_name]
camp = camps[camp_index]
camp_id = camp["camp_id"]

# camp_start_date, camp_end_date는 문자열이라고 가정 ("YYYY-MM-DD")
camp_start_date = datetime.strptime(camp["start_date"][:10], "%Y-%m-%d")
camp_end_date = datetime.strptime(camp["end_date"][:10], "%Y-%m-%d")

selected_date: datetime = st.sidebar.date_input(
    "기준 날짜 선택",
    value=camp_start_date,       # 기본값: 캠프 시작일
    min_value=camp_start_date,   # 최소: 캠프 시작
    max_value=camp_end_date,     # 최대: 캠프 종료
)

# ============================================
# 1-1. 사이드바: 출결 규칙 저장/조회
# ============================================
st.sidebar.markdown("---")
st.sidebar.subheader("🧾 출결 규칙")

ruleset_cache = session_cache["attendance_rulesets"]
ruleset_raw_cache = session_cache["attendance_ruleset_raw"]

# 1) 세션 캐시에서 먼저 가져오기
ruleset_payload = ruleset_cache.get(camp_id)

# 2) 캐시에 없으면 서버에서 조회해서 세션에 저장
if ruleset_payload is None:
    try:
        ruleset_payload = get_attendance_ruleset(camp_id)
    except Exception:
        ruleset_payload = None

    if ruleset_payload:
        ruleset_cache[camp_id] = ruleset_payload

# 텍스트 입력 기본값 (서버 GET에는 raw_rules_text가 없으니, 클라가 마지막 저장한 값을 유지)
default_raw = ruleset_raw_cache.get(camp_id, "")

raw_rules_text = st.sidebar.text_area(
    "규칙 입력 (자연어로 작성 가능)",
    value=default_raw,
    height=180,
    placeholder=(
        "- 지각 기준: 09:10 이후 접속\n"
        "- 조퇴 기준: 17:00 이전 종료\n"
        "- 결석 기준: 당일 접속 기록 없음\n"
        "- 이상활동: 접속은 했지만 활동 시간이 10분 미만\n"
    ),
)

save_rules_clicked = st.sidebar.button("규칙 저장하기", use_container_width=True)

if save_rules_clicked:
    if not raw_rules_text.strip():
        st.sidebar.warning("규칙 내용을 입력해 주세요.")
    else:
        with st.spinner("규칙을 저장하고 컴파일 중입니다..."):
            try:
                saved = save_attendance_ruleset(
                    camp_id=camp_id,
                    raw_rules_text=raw_rules_text.strip(),
                )
                session_cache["attendance_rulesets"][camp_id] = saved
                session_cache["attendance_ruleset_raw"][camp_id] = raw_rules_text.strip()
                st.sidebar.success("규칙 저장 완료!")
            except Exception as e:
                st.sidebar.error(f"저장 실패: {e}")

# 현재 활성 규칙(컴파일 결과) 표시
ruleset_payload = session_cache["attendance_rulesets"].get(camp_id)
if ruleset_payload:
    with st.sidebar.expander("현재 적용 중인 규칙 보기"):
        st.markdown(ruleset_payload.get("raw_text", ""))
else:
    st.sidebar.caption("아직 저장된 규칙이 없습니다.")

st.sidebar.markdown("---")

# ============================================
# 2-2. 출결 리포트 조회 및 생성
# ============================================
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
generate_clicked = st.sidebar.button("리포트 생성하기", use_container_width=True)
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

# st.json(payload)
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
students_raw = payload.get("students_stat", []) or []
top_ops_actions = summary.get("top_ops_actions", [])
# st.json(summary)

if not students_raw:
    st.warning("학생별 출결 리포트가 아직 없습니다.")
    st.stop()

df = pd.DataFrame(students_raw)

# 안전한 기본값 처리
if "risk_level" not in df.columns:
    df["risk_level"] = "정상"
if "pattern_type" not in df.columns:
    df["pattern_type"] = ""
if "ops_action" not in df.columns:
    df["ops_action"] = ""

def display_report():
    st.title("출결 리포트", text_alignment="center")

    # ============================================
    # 3. 페이지 타이틀 및 요약
    # ============================================

    # =========================================================
    # 이번 주 리포트
    # =========================================================
    st.subheader(f"[{camp_name}] {selected_date} 출결 리포트", text_alignment="center")
    st.markdown(f"{camp_start_date} ~ {selected_date} 출결을 분석한 결과입니다.", text_alignment="center")
    st.markdown("---")


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
    risk_count = summary.get(
        "risk_count",
        int((df["risk_level"] == "위험").sum()),
    )
    caution_count = summary.get(
        "caution_count",
        int((df["risk_level"] == "주의").sum()),
    )
    total_students = summary.get("total_students", len(df))

    left, _, right = st.columns([1, 0.2, 1.5])

    # 1) 왼쪽: 출석률 파이차트
    with left:
        st.markdown("#### 🥧 출석률")

        if attendance_rate is None:
            st.info("출석률 데이터가 없습니다.")
        else:
            present = max(0.0, min(1.0, float(attendance_rate)))
            absent = 1.0 - present

            pie_df = pd.DataFrame(
                [
                    {"label": "출석", "value": present},
                    {"label": "미출석", "value": absent},
                ]
            )

            # 파이차트
            pie = (
                alt.Chart(pie_df)
                .mark_arc(innerRadius=70)  # 🔥 도넛 형태로 만들어 중앙 공간 확보
                .encode(
                    theta=alt.Theta(field="value", type="quantitative"),
                    color=alt.Color(field="label", type="nominal", legend=None),
                    tooltip=[
                        alt.Tooltip("label:N", title="구분"),
                        alt.Tooltip("value:Q", title="비율", format=".1%"),
                    ],
                )
            )

            # 중앙 텍스트 (출석률 %)
            center_text = (
                alt.Chart(
                    pd.DataFrame(
                        {"text": [f"{present*100:.1f}%"]}
                    )
                )
                .mark_text(fontSize=26, fontWeight="bold")
                .encode(text="text:N")
            )

            chart = pie + center_text

            st.altair_chart(chart, use_container_width=True)
            st.caption("전체 참여일 기준 출석률")
    # 2) 오른쪽: 고위험/위험/주의 게이지
    with right:
        st.markdown("#### 🚨 위험 분포 (고위험/위험/주의)")

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("전체", f"{total_students}명")
        with c2:
            st.metric("고위험", f"{high_risk_count}명")
        with c3:
            st.metric("위험", f"{risk_count}명")
        with c4:
            st.metric("주의", f"{caution_count}명")

        # 게이지 데이터
        level_data = [
            {"level": "고위험", "count": int(high_risk_count)},
            {"level": "위험", "count": int(risk_count)},
            {"level": "주의", "count": int(caution_count)},
        ]

        # make_ratio_gauge는 너가 이미 가지고 있는 함수 사용
        gauge = make_ratio_gauge(
            data=level_data,
            label_col="level",
            count_col="count",
            bar_label="고위험/위험/주의 분포",
            color_map=None,   # ✅ 색 지정 안 함(너 규칙)
            font_size=15,
        )

        if gauge is not None:
            st.altair_chart(gauge, use_container_width=True)
            st.caption("전체 학생 중 위험 레벨 비율")
        else:
            st.info("게이지를 그릴 데이터가 없습니다.")

        def draw_attendance_trend_sparkline(df: pd.DataFrame) -> None:
            st.markdown("#### 📉 최근 출결 추세")

            if df is None or len(df) == 0:
                st.info("학생 데이터가 없습니다.")
                return

            # df에 students의 attendance_records가 들어있다고 가정
            # attendance_records: [{"date":"2025-11-03", "attendance_type":"ON_TIME"}, ...]
            if "attendance_records" not in df.columns:
                st.info("attendance_records가 없어 스파크라인을 만들 수 없습니다.")
                return

            # 1) 최근 30일 날짜별 "출석자 비율" 계산
            rows = []
            for _, r in df.iterrows():
                recs = r.get("attendance_records") or []
                for rec in recs:
                    rows.append({
                        "date": rec.get("date", "")[:10],
                        "atype": rec.get("attendance_type", ""),
                    })

            if not rows:
                st.info("출결 기록이 없습니다.")
                return

            rec_df = pd.DataFrame(rows)
            rec_df["date"] = pd.to_datetime(rec_df["date"], errors="coerce")
            rec_df = rec_df.dropna(subset=["date"])

            if rec_df.empty:
                st.info("출결 기록 날짜 파싱 실패")
                return

            # ✅ 최근 30일만
            max_day = rec_df["date"].max()
            min_day = max_day - pd.Timedelta(days=29)
            rec_df = rec_df[(rec_df["date"] >= min_day) & (rec_df["date"] <= max_day)]

            # ✅ 출석으로 치는 타입: ON_TIME/LATE/EARLY_LEAVE (ABSENT/UNKNOWN 제외)
            present_types = {"ON_TIME", "LATE", "EARLY_LEAVE"}
            rec_df["is_present"] = rec_df["atype"].isin(present_types).astype(int)

            daily = (
                rec_df.groupby("date")["is_present"]
                .mean()  # 학생 전체에서 그날 출석 비율
                .reset_index()
                .rename(columns={"is_present": "rate"})
                .sort_values("date")
            )

            # 3) 스파크라인 (컴팩트 + 꼭짓점 수치 표시)
            base = alt.Chart(daily, height=80)

            line = base.mark_line(strokeWidth=2).encode(
                x=alt.X("date:T", title=None, axis=alt.Axis(labels=False, ticks=False)),
                y=alt.Y(
                    "rate:Q",
                    title=None,
                    axis=alt.Axis(format="%", tickCount=3),
                    scale=alt.Scale(domain=[0, 1]),
                ),
            )

            points = base.mark_point(size=40).encode(
                x="date:T",
                y="rate:Q",
            )

            labels = base.mark_text(
                dy=-8,              # ✅ 포인트 위로 살짝
                fontSize=10,
                color="#444",
            ).encode(
                x="date:T",
                y="rate:Q",
                text=alt.Text("rate:Q", format=".0%"),  # ✅ 퍼센트 표시
            )

            chart = line + points + labels

            st.altair_chart(chart, use_container_width=True)
            st.caption("최근 30일 일별 출석률")
        
        draw_attendance_trend_sparkline(df)
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
                name = row.get("name", f"학생 {row.get('user_id', '')}")
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

    # st.markdown("### 🏃 운영진 우선 액션 Top 3")

    # def build_ops_actions_for_attendance(df: pd.DataFrame):
    #     actions = []

    #     # 1) 고위험자 있으면: 1:1 케어
    #     high_risk_df = df[df["risk_level"] == "고위험"]
    #     if not high_risk_df.empty:
    #         names = ", ".join(high_risk_df["name"].astype(str).head(3).tolist())
    #         actions.append(
    #             {
    #                 "title": "1. 고위험 학생 1:1 체크인",
    #                 "target": f"고위험 학생: {names} ...",
    #                 "reason": f"고위험으로 분류된 학생이 총 {len(high_risk_df)}명입니다.",
    #                 "todo": (
    #                     "각 학생에게 개별적으로 현재 상황을 묻는 체크인 메시지를 보내고, "
    #                     "필요 시 15~20분 정도의 간단한 1:1 상담 시간을 제안합니다."
    #                 ),
    #             }
    #         )

    #     # 2) 위험/주의 학생이 많으면: 그룹 케어
    #     warn_df = df[df["risk_level"].isin(["위험", "주의"])]
    #     if not warn_df.empty:
    #         actions.append(
    #             {
    #                 "title": "2. 주의/위험 학생 그룹 케어 세션",
    #                 "target": "주의/위험 등급 학생 전체",
    #                 "reason": f"주의/위험 등급 학생이 총 {len(warn_df)}명입니다.",
    #                 "todo": (
    #                     "공통된 어려움이 있는지 파악하기 위해 3~5명 단위 그룹으로 짧은 케어 세션을 진행하고, "
    #                     "진도/과제 난이도/시간 관리 측면에서 지원이 필요한 부분을 함께 정리합니다."
    #                 ),
    #             }
    #         )

    #     # 3) 전체 출석률이 낮으면: 공지/환경 개선
    #     avg_att = df["attendance_rate"].mean() if "attendance_rate" in df.columns else None
    #     if avg_att is not None and avg_att < 0.8:
    #         actions.append(
    #             {
    #                 "title": "3. 전체 출석률 저하 공지 및 참여 동기 재강조",
    #                 "target": "전체 수강생",
    #                 "reason": f"누적 평균 출석률이 {avg_att*100:.1f}%로 낮은 편입니다.",
    #                 "todo": (
    #                     "현재 출석 현황을 간단히 공유하고, 출석이 학습성과와 어떤 관련이 있는지 안내합니다. "
    #                     "또한 매일 시작 5분 전 리마인드 공지를 보내 출석률을 끌어올립니다."
    #                 ),
    #             }
    #         )

    #     return actions[:3]

    # ops_actions = build_ops_actions_for_attendance(df)

    # if ops_actions:
    #     cols = st.columns(len(ops_actions))
    #     for idx, action in enumerate(ops_actions):
    #         with cols[idx]:
    #             with st.container(border=True):
    #                 st.markdown(f"#### {action['title']}")
    #                 st.markdown(f"- **대상**: {action['target']}")
    #                 st.markdown(f"- **근거**: {action['reason']}")
    #                 st.markdown("**이번 기준일까지 실행하면 좋은 액션**")
    #                 st.markdown(action["todo"])
    # else:
    #     st.info("현재 데이터 기준으로 별도의 우선 액션 제안은 없습니다.")

    # st.markdown("---")


col1, col2 = st.columns([1,0.5])

with col1:
    with st.container(height=600, border=False):
        display_report()
with col2: 
    with st.container(height=600, border=True):
        display_chatbot()

# ============================================
    # 6. 출결 상세 테이블 (운영진 조치 칼럼 포함)
# ============================================

st.markdown("### 📂 출결 요약 테이블")

columns_map = {
    "name": "이름",
    "attendance_rate": "출석률",
    "absent_count": "결석",
    "late_count": "지각",
    "early_leave_count": "조퇴",
    "pattern_type": "출결 패턴",
    "personality_type": "성향",
    "risk_level": "위험 등급",
    "trend": "최근 변화율",
    "ops_action": "운영진 조치",
}
show_cols = [c for c in columns_map.keys() if c in df.columns]

display_df = df[show_cols].rename(columns=columns_map)
display_df["운영진 조치"] = display_df["운영진 조치"].str.replace(
    ". ", ".\n", regex=False
)
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
            width="large", 
        ),
    },
)

# ============================================
# 7. 날짜별 출결 매트릭스 테이블 (날짜=열, 학생=행)
#    ✅ 주말 제외 + ✅ 요일 표시
# ============================================

import pandas as pd
from datetime import date

st.markdown("---")
st.markdown("### 🗓️ 날짜별 출결 상세")

# 1) 날짜 범위 만들기: 캠프 시작일 ~ 선택일 (inclusive)
start_day = camp_start_date.date()
end_day = selected_date if isinstance(selected_date, date) else selected_date.date()

# ✅ 주말 제외: freq="B" (Business day = 월~금)
all_days = pd.date_range(start=start_day, end=end_day, freq="B")

# ✅ 내림차순: 최신 날짜가 왼쪽부터 오게
all_days_desc = list(reversed(all_days))

# 2) 표에 들어갈 날짜 컬럼명 만들기: "YYYY-MM-DD(요일)"
weekday_kr = ["월", "화", "수", "목", "금", "토", "일"]

date_cols = [
    f"{d.strftime('%Y-%m-%d')}({weekday_kr[d.weekday()]})"
    for d in all_days_desc
]

# 🔥 rec_map은 'YYYY-MM-DD'로 되어 있으니,
# 컬럼명(요일 포함) -> 날짜키('YYYY-MM-DD') 매핑을 만들어서 조회에 사용
col_to_datekey = {col: col[:10] for col in date_cols}

# 3) 출결 타입 표시 스타일 (아이콘)
def format_attendance_cell(att_type: str) -> str:
    """
    attendance_records의 attendance_type 값을 표 셀 아이콘으로 표시
    """
    mapping = {
        "ON_TIME": "✅",       # 출석
        "LATE": "⏰",          # 지각
        "EARLY_LEAVE": "🏃",   # 조퇴
        "ABSENT": "❌",        # 결석
        "UNKNOWN": "❓",       # 미확인
        None: "",
        "": "",
    }
    return mapping.get(att_type, "❓")

# 4) students_stat 기반으로 "학생별 (date -> attendance_type)" 맵 만들기
#    attendance_records: [{"date":"2025-11-03", "attendance_type":"PRESENT"}, ...]
student_rows = []
for _, r in df.iterrows():
    name = r.get("name", f"학생 {r.get('user_id', '')}")
    recs = r.get("attendance_records") or []

    # 날짜별 타입 dict로 변환
    rec_map = {}
    for rec in recs:
        dt_str = (rec.get("date") or "")[:10]  # 'YYYY-MM-DD'
        atype = rec.get("attendance_type")
        if dt_str:
            rec_map[dt_str] = atype

    row = {"이름": name}

    # ✅ 날짜는 최신 -> 과거 순서로 컬럼 채우기 (주말 제외 + 요일 표기)
    for col in date_cols:
        date_key = col_to_datekey[col]  # 'YYYY-MM-DD'
        row[col] = format_attendance_cell(rec_map.get(date_key, ""))  # 없으면 공백

    student_rows.append(row)

matrix_df = pd.DataFrame(student_rows)

# (선택) 보기 좋게: 이름을 인덱스로 두고 싶으면
# matrix_df = matrix_df.set_index("이름")

# 5) 렌더링 (가로로 길어질 테니 wide + container_width)
st.dataframe(
    matrix_df,
    use_container_width=True,
    hide_index=True,
)

st.caption("표기: ✅ 출석 / ⏰ 지각 / 🏃 조퇴 / ❌ 결석 / ❓ 미확인")

st.json(payload)