import streamlit as st
import pandas as pd
import altair as alt

from streamlit_app.api.curriculum import (
    analyze_curriculum_text,
    fetch_curriculum_config,
    save_curriculum_config,
)
from streamlit_app.api.camp import fetch_camps

st.set_page_config(layout="wide")
st.title("📚 커리큘럼 분석")

# --------------------------------
# 0) 세션 기반 데이터 캐시 설정
# --------------------------------
if "curriculum_session" not in st.session_state:  # 한 번만 초기화
    st.session_state["curriculum_session"] = {
        "camps": None,                       # fetch_camps() 결과
        "camp_name_to_id": None,            # {name: id}
        "curriculum_config_by_camp": {},    # {camp_id: config}
        "curriculum_reports": {},           # {f"{camp_id}_{week_index}": payload}
    }

session_cache = st.session_state["curriculum_session"]

# --- 캠프 목록은 세션에 한 번만 저장 ---
if session_cache["camps"] is None:
    res = fetch_camps()  # [{camp_id, name, start_date, end_date, ...}, ...] 가정
    camps = res.get("camps", [])
    camp_name_to_id = {c["name"]: c["camp_id"] for c in camps}
    session_cache["camps"] = camps
    session_cache["camp_name_to_id"] = camp_name_to_id
else:
    camps = session_cache["camps"]
    camp_name_to_id = session_cache["camp_name_to_id"]

# --------------------------------
# 1) 캠프 목록 / 주차 선택
# --------------------------------
st.sidebar.header("필터 설정")

camp_name = st.sidebar.selectbox("반 선택", list(camp_name_to_id.keys()))
camp_id = camp_name_to_id[camp_name]

weeks = ["Week 1", "Week 2", "Week 3", "Week 4", "Week 5", "Week 6"]
selected_week_label = st.sidebar.selectbox("주차 선택", weeks)
week_index = int(selected_week_label.split()[1])  # "Week 3" -> 3
week_label = f"{week_index}주차"

# --------------------------------
# 2) 커리큘럼 구조 자동 분석
# --------------------------------
config_cache = session_cache["curriculum_config_by_camp"]
preview_container = st.container()

config = config_cache.get(camp_id)
if config is None:
    config = fetch_curriculum_config(camp_id=camp_id) or {}
    config_cache[camp_id] = config

tab_analyze, tab_edit = st.tabs(
    ["자동 분석", "수동 수정"]
)

with tab_analyze:
    existing_weeks = config.get("weeks", [])

    st.markdown("####  커리큘럼 텍스트 자동 분석")

    raw_text = st.text_area(
        "커리큘럼 전체 설명을 붙여넣어 주세요. (1주차 ~ N주차)",
        height=180,
        key="curriculum_raw_text",
        placeholder=(
            "예시)\n"
            "1주차: 파이썬 기초, 자료형, 조건문, 반복문\n"
            "2주차: Numpy / Pandas 데이터 처리\n"
            "3주차: 시각화, Matplotlib, EDA 프로젝트\n"
            "4주차: NLP 네트워크, 연관어 분석 ..."
        ),
    )

    col_auto_1, col_auto_2 = st.columns([2, 3])
    with col_auto_1:
        if st.button("🧠 분석하기", use_container_width=True):
            config_cache[camp_id] = {}
            if raw_text.strip():
                with st.spinner("LLM으로 커리큘럼 구조 분석 중..."):
                    auto_config = analyze_curriculum_text(
                        camp_id=camp_id,
                        raw_text=raw_text,
                    )
                    
                    config_cache[camp_id] = auto_config
                    existing_weeks = auto_config.get("weeks", [])
                    st.success("커리큘럼 텍스트를 기반으로 주차별 구조를 자동 완성했어요.")
            else:
                st.warning("커리큘럼 텍스트를 먼저 입력해 주세요.")

with tab_edit:
    st.markdown("#### 주차별 커리큘럼 직접 수정")

    existing_weeks = config_cache.get(camp_id, {}).get("weeks", [])

    if existing_weeks:
        default_week_count = max([w.get("week_index", 0) for w in existing_weeks] + [1])
    else:
        default_week_count = 6

    week_count = st.number_input(
        "주차 수",
        min_value=1,
        max_value=30,
        value=default_week_count,
        step=1,
        key="curriculum_week_count",
    )

    new_weeks = []

    for i in range(1, week_count + 1):
        existing = next((w for w in existing_weeks if w.get("week_index") == i), None)
        default_label = existing.get("week_label") if existing else f"{i}주차"
        default_topics = ",".join(existing.get("topics", [])) if existing else ""

        with st.expander(f"{i}주차 설정", expanded=(i == 1)):
            week_label_input = st.text_input(
                f"{i}주차 라벨",
                value=default_label,
                key=f"week_label_{camp_id}_{i}",
            )
            topic_raw = st.text_input(
                f"{i}주차 토픽 키 (쉼표 구분, 예: python_basics,pandas)",
                value=default_topics,
                key=f"week_topics_{camp_id}_{i}",
            )
            topics = [t.strip() for t in topic_raw.split(",") if t.strip()]

            new_weeks.append(
                {
                    "week_index": i,
                    "week_label": week_label_input,
                    "topics": topics,
                }
            )

    if st.button("💾 커리큘럼 저장", use_container_width=True, key="save_curriculum_btn"):
        config_cache[camp_id] = {}
        save_curriculum_config(
            camp_id=camp_id,
            weeks=new_weeks,
        )
        config_cache[camp_id] = {
            "weeks": new_weeks,
        }
        st.success("커리큘럼 구조를 저장했어요.")

with preview_container:
    st.markdown("#### 현재 커리큘럼 구조 미리보기")

    latest_config = config_cache.get(camp_id, {})
    existing_weeks = latest_config.get("weeks", [])

    if existing_weeks:
        df_weeks = pd.DataFrame(existing_weeks)
        st.dataframe(df_weeks, hide_index=True, use_container_width=True)
    else:
        st.info("아직 저장된 커리큘럼 구조가 없습니다. 자동 세팅이나 직접 입력 후 저장해 주세요.")
