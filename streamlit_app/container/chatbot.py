import streamlit as st
import requests

from streamlit_app.api.chat import send_chat

def display_chatbot():
    # 세션 채팅 로그
    if "dispatch_chat" not in st.session_state:
        st.session_state['dispatch_chat'] = []

    # 채팅 로그 렌더
    for msg in st.session_state['dispatch_chat']:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # 입력
    user_input = st.chat_input("예: 머물머물 캠프로 QR 코드 출결 공지 보내줘")

    if user_input:
        # 1) 화면에 유저 메시지 표시
        st.session_state['dispatch_chat'].append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        # 2) API 호출
        with st.chat_message("assistant"):
            with st.spinner("AI가 생각중..."):
                try:
                    resp = send_chat(user_input)
                    if resp.status_code != 200:
                        st.error(f"서버 에러: {resp.status_code}\n{resp.text}")
                        st.session_state.dispatch_chat.append({
                            "role": "assistant",
                            "content": f"❌ 서버 에러 ({resp.status_code})\n\n{resp.text}",
                        })
                    else:
                        data = resp.json()

                        # 보기 좋게 출력
                        st.success("✅ 전송 요청 완료")
                        st.json(data)  # 결과 전체 표시 (디버그에 최고)

                        st.session_state.dispatch_chat.append({
                            "role": "assistant",
                            "content": f"✅ 전송 완료\n\n```json\n{data}\n```",
                        })

                except requests.exceptions.RequestException as e:
                    st.error(f"요청 실패: {e}")
                    st.session_state.dispatch_chat.append({
                        "role": "assistant",
                        "content": f"❌ 요청 실패: {e}",
                    })
