import streamlit as st
import requests

from streamlit_app.api.chat import send_chat

def display_chatbot():
    with st.container(height=480, border=False):
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
                        # st.success("✅ 전송 요청 완료")
                        # st.json(data)  # 결과 전체 표시 (디버그에 최고)

                        # DM 전송 결과 등 원하는 정보만 추출하여 표시 가능
                        # DM 형태 {'status': 'success', 'detail': {'sender_id': 1, 'request_text': '윤여민 학생에게 당분 섭취를 너무 많이하면 건강에 나쁘다고 염려의 DM을 보내줘', 'current_time': '2025-12-29T08:03:23.827417+00:00', 'parsed': {'message_type': 'dm', 'target_scope': 'user_list', 'camp_name': None, 'user_names': ['윤여민'], 'topic': '당분 섭취 과다', 'requested_user_ids': None, 'target_query': None, 'delivery_channel': 'websocket', 'urgency': 'normal', 'language': 'ko'}, 'camp_id': 1, 'target_user_ids': [6], 'dm_messages': [{'user_id': 6, 'user_name':"윤여민", 'message_text': '여민님, 요즘 당분 섭취가 많으면 피로, 체중 증가, 구강 문제 등 건강에 영향을 줄 수 있어요. 지금 바로 할 수 있는 방법으로는 음료를 무가당으로 바꾸고, 과자 대신 견과류나 신선한 과일로 대체해 보세요. 컵 크기를 줄이거나 일주일 중 3일간 섭취 기록을 해보면 조절하기 수월합니다. 필요하면 간단한 실천 계획 같이 만들어드릴게요.', 'personality_tone': 'concise'}], 'dispatch_result': {'attempted': 1, 'sent': 1, 'failed': 0, 'channel': 'websocket'}, 'error': None, 'debug': {}}}
                        detail = data.get('detail', {})
                        parsed = detail.get('parsed', {})
                        message_type = parsed.get('message_type', 'N/A')
                        if message_type == 'dm':
                            for dm in detail.get('dm_messages', []):
                                user_name = dm.get('user_name', 'N/A')
                                message_text = dm.get('message_text', 'N/A')
                                st.markdown(f"✅ 전송 요청 완료\n\n**{user_name}** 님에게 보낼 DM:\n\n{message_text}")
                                st.session_state.dispatch_chat.append({
                                    "role": "assistant",
                                    "content": f"✅ 전송 요청 완료\n\n**{user_name}** 님에게 보낼 DM:\n\n{message_text}",
                                })

                                # 실제 보낼지 여부를 체크하는 버튼
                                send_button = st.button(f"{user_name}님에게 DM 전송", key=f"send_dm_{user_name}")
                                if send_button:
                                    # 여기에 실제 DM 전송 로직 추가
                                    st.success(f"✅ {user_name}님에게 DM 전송 완료")
                                    st.session_state.dispatch_chat.append({
                                        "role": "assistant",
                                        "content": f"✅ {user_name}님에게 DM 전송 완료",
                                    })
                        elif message_type == 'notice':
                            notice_content = detail.get('notice_message', 'N/A')
                            title = detail.get('notice_message', {}).get('title', '공지')
                            messamessage_textge = detail.get('notice_message', {}).get('message_text', 'N/A')
                            st.markdown(f"✅ 전송 요청 완료\n\n공지 내용:\n\n{message_text}")
                            st.session_state.dispatch_chat.append({
                                "role": "assistant",
                                "content": f"✅ 전송 요청 완료\n\n공지 내용:\n\n{notice_content}",
                            })
                        else:
                            st.markdown("⚠️ 지원하지 않는 메시지 유형입니다.")
                            st.session_state.dispatch_chat.append({
                                "role": "assistant",
                                "content": "⚠️ 지원하지 않는 메시지 유형입니다.",
                            })
                        
                except requests.exceptions.RequestException as e:
                    st.error(f"요청 실패: {e}")
                    st.session_state.dispatch_chat.append({
                        "role": "assistant",
                        "content": f"❌ 요청 실패: {e}",
                    })
