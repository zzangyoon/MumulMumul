import streamlit as st
from streamlit_app.api.camp import fetch_camps

def get_camp_session() -> dict:
    """캠프 관련 세션 상태를 초기화하고 반환합니다."""
    if "curriculum_session" not in st.session_state:  # 한 번만 초기화
        st.session_state["camp_session"] = {
            "camps": None,                       # fetch_camps() 결과를 {id: camp_dict} 형태로 저장
            "camp_name_to_id": None,            # {name: id}
        }

    camp_session_cache = st.session_state["camp_session"]

    # --- 캠프 목록은 세션에 한 번만 저장 ---
    if camp_session_cache["camps"] is None:
        res = fetch_camps()  # [{camp_id, name, start_date, end_date, ...}, ...] 가정
        camps = res.get("camps", [])
        st.session_state["camp_session"]["camps"] = {c["camp_id"]: c for c in camps}
        st.session_state["camp_session"]["camp_name_to_id"] = {
            c["name"]: c["camp_id"] for c in camps
        }

    return st.session_state["camp_session"]