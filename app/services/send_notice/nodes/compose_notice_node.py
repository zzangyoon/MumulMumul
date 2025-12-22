from pydantic import BaseModel, Field
from typing import Literal, Optional

import sys
from pathlib import Path

CURRENT_FILE = Path(__file__).resolve()
ROOT_DIR = CURRENT_FILE.parents[4]
sys.path.append(str(ROOT_DIR))

from langchain.agents import create_agent

from app.core.models import openai_chat_model
from app.services.send_notice.schemas import MessagingAgentState, ComposeNoticeResult


def compose_messages_node(state: MessagingAgentState) -> MessagingAgentState:
    print("\n==============================")
    print("[NODE] compose_messages_node START")

    try:
        if not state.parsed:
            raise ValueError("parsed is None (parse_request_node first)")

        if not state.target_user_ids:
            raise ValueError("target_user_ids is empty (select_targets_node first)")

        parsed = state.parsed
        target_count = len(state.target_user_ids)

        print("[STATE] camp_name =", parsed.camp_name)
        print("[STATE] topic =", parsed.topic)
        print("[STATE] urgency =", parsed.urgency)
        print("[STATE] target_user_ids count =", target_count)

        llm = openai_chat_model()

        # tools 없이도 됨(공지 생성은 보통 tool 불필요)
        # 필요하면 이후 "공지 템플릿 가져오기" 같은 tool을 추가해 확장 가능
        tools = []

        agent = create_agent(
            model=llm,
            tools=tools,
            response_format=ComposeNoticeResult,   # ✅ Pydantic 강제
            system_prompt=(
                "너는 부트캠프 운영진을 위한 공지 작성 어시스턴트다.\n"
                "운영진이 그대로 복사해서 발송할 수 있는 공지문을 작성해라.\n\n"
                "작성 규칙:\n"
                "- 한국어로 작성\n"
                "- 한 번에 이해되게 간결하게\n"
                "- 핵심: 무엇을/언제까지/어떻게 해야 하는지\n"
                "- 필요하면 체크리스트(불릿) 사용\n"
                "- 대상자 수/캠프명은 자연스럽게 반영\n"
                "- 긴급 공지(urgency=high)면 톤을 더 단호하게\n"
                "- 최종 출력은 response_format 스키마를 따른 구조화 결과로만 낸다\n"
            ),
        )

        user_content = (
            f"캠프명: {parsed.camp_name}\n"
            f"공지 주제: {parsed.topic}\n"
            f"대상자 수: {target_count}명\n"
            f"긴급도: {parsed.urgency}\n\n"
            "이 조건에 맞춰 공지 제목과 본문을 작성해줘."
        )

        print("[LLM] compose_messages_node invoke")
        result = agent.invoke({
            "messages": [{"role": "user", "content": user_content}]
        })

        composed: ComposeNoticeResult = result["structured_response"]

        print("[LLM] compose_messages_node structured_response =")
        print(composed.model_dump())

        # state 반영
        state.notice_message = composed
        state.error = None

        print("[STATE] message_text length =", len(state.message_text or ""))
        print("[NODE] compose_messages_node END")
        return state

    except Exception as e:
        print("[ERROR] compose_messages_node failed")
        print(e)
        state.error = f"compose_messages_node failed: {e}"
        state.message_text = None
        return state
