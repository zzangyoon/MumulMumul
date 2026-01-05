# streamlit 앱 진입점
from __future__ import annotations
import streamlit as st

from streamlit_app.api.camp import fetch_camps
from streamlit_app.session import get_camp_session

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


camp_session_cache = get_camp_session()