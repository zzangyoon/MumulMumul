# streamlit 앱 진입점
from __future__ import annotations
import streamlit as st

from streamlit_app.api.camp import fetch_camps

st.set_page_config(
    page_title="머물머물 운영자 대시보드",
    page_icon="🖥️",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🔥 머물머물 운영 리포트 대시보드")
st.markdown(
    """
왼쪽 사이드바에서 아래 3가지 리포트 페이지를 이동하며 구조를 확인할 수 있어요.

1. 속닥숲 리포트: 캠프별/주차별 속닥숲 글 분석 결과 요약
2. 출결 리포트: 캠프별/주차별 출결 현황 요약
3. 커리큘럼 분석: 캠프별/주차별 커리큘럼 텍스트 분석 결과
4. 학습 리포트: 캠프별/주차별 학습챗봇 대화 분석 결과
"""
)

st.info("좌측 사이드바의 `pages` 메뉴에서 각 리포트 페이지를 선택해 레이아웃을 확인해보세요.")


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
