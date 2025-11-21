# streamlit 앱 진입점
from __future__ import annotations
import streamlit as st

st.set_page_config(
    page_title="머물머물 관리자 대시보드",
    page_icon="🖥️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# pages = [
#     st.Page(
#         page="pages/example.py",
#         title="example",
#         icon="📃",
#         default=True,
#         url_path="example",
#     ),
#     st.Page(
#         page="pages/overview.py",
#         title="1_overview",
#         icon="🖥️",
#         default=False,
#         url_path="overview",
#     ),
#     st.Page(
#         page="pages/team_and_user.py",
#         title="2_team_and_user",
#         icon="👥",
#         default=False,
#         url_path="team_and_user",
#     ),
#     st.Page(
#         page="pages/risk_and_community.py",
#         title="3_risk_and_community",
#         icon="🚨",
#         default=False,
#         url_path="risk_and_community",
#     ),
# ]

# nav = st.navigation(pages)
# nav.run()

st.title("🔥 머물머물 운영 리포트 대시보드")
st.markdown(
    """
이 화면은 **레이아웃 확인용 더미 버전**입니다.  
왼쪽 사이드바에서 아래 3가지 리포트 페이지를 이동하며 구조를 확인할 수 있어요.

1. **익명 게시판 분석** – 건의/문제 파악, 분위기 흐름  
2. **학습 난이도·커리큘럼 병목 분석** – 어디서 막히는지  
3. **출결 및 이탈 위험 분석** – 누구를 케어해야 하는지  

실제 데이터/LLM 연동은 이후 단계에서 추가합니다.
"""
)

st.info("좌측 사이드바의 `pages` 메뉴에서 각 리포트 페이지를 선택해 레이아웃을 확인해보세요.")