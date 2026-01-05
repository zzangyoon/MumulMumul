import streamlit as st
import requests

from streamlit_app.api.chat import send_chat

def display_chatbot():
    # 세션 채팅 로그
    if "dispatch_chat" not in st.session_state:
        st.session_state["dispatch_chat"] = []

    # ✅ 채팅 로그를 렌더링할 자리(placeholder)
    chat_area = st.container(height=480, border=False)

    # 입력
    user_input = st.chat_input("예: 머물머물 캠프로 QR 코드 출결 공지 보내줘")

    if user_input:
        # 1) 유저 메시지 저장
        st.session_state["dispatch_chat"].append({"role": "user", "content": user_input})

        # 2) API 호출 + 결과 저장
        with st.spinner("AI가 생각중..."):
            try:
                resp = send_chat(user_input)

                if resp.status_code != 200:
                    st.session_state["dispatch_chat"].append({
                        "role": "assistant",
                        "content": f"❌ 서버 에러 ({resp.status_code})\n\n{resp.text}",
                    })
                else:
                    data = resp.json()
                    detail = data.get("detail", {})
                    parsed = detail.get("parsed", {})
                    message_type = parsed.get("message_type", "N/A")

                    if message_type == "dm":
                        for dm in detail.get("dm_messages", []):
                            user_name = dm.get("user_name", "N/A")
                            message_text = dm.get("message_text", "N/A")
                            st.session_state["dispatch_chat"].append({
                                "role": "assistant",
                                "content": f"✅ 전송 요청 완료\n\n**{user_name}** 님에게 보낼 DM:\n\n{message_text}",
                            })

                    elif message_type == "notice":
                        title = detail.get("notice_message", {}).get("title", "공지")
                        message_text = detail.get("notice_message", {}).get("message_text", "N/A")
                        st.session_state["dispatch_chat"].append({
                            "role": "assistant",
                            "content": f"✅ 전송 요청 완료\n\n**{title}**\n\n{message_text}",
                        })

                    else:
                        st.session_state["dispatch_chat"].append({
                            "role": "assistant",
                            "content": "⚠️ 지원하지 않는 메시지 유형입니다.",
                        })

            except requests.exceptions.RequestException as e:
                st.session_state["dispatch_chat"].append({
                    "role": "assistant",
                    "content": f"❌ 요청 실패: {e}",
                })

        # ✅ 입력 처리 후 즉시 rerun 하면 UX가 더 깔끔해짐(선택)
        st.rerun()

    # ✅ 항상 “마지막”에 채팅 로그를 렌더 (그래야 최신 상태가 위에 뜸)
    with chat_area:
        for msg in st.session_state["dispatch_chat"]:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
