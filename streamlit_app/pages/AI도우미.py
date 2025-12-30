from streamlit_app.container.chatbot import display_chatbot
import streamlit as st

from streamlit_app.session import get_camp_session

st.title("🤖 AI 도우미")

camp_session_cache = get_camp_session()

display_chatbot()