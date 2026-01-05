# app/services/send_dispatch/nodes/compose_dm_node.py
import sys
from pathlib import Path

from app.core.schemas import User
from app.services.db_service.tendency_profiles import get_tendency_profiles_context
from app.services.db_service.user import get_tendancy_code_for_user, get_user_by_id

CURRENT_FILE = Path(__file__).resolve()
ROOT_DIR = CURRENT_FILE.parents[4]
sys.path.append(str(ROOT_DIR))

from typing import List
from langchain.agents import create_agent

from app.core.models import openai_chat_model
from app.services.send_dispatch.schemas import ComposeDM, MessagingAgentState, ComposeDMResult


def compose_dm_node(state: MessagingAgentState) -> MessagingAgentState:
    print("\n==============================")
    print("[NODE] compose_dm_node START")

    try:
        if not state.parsed:
            raise ValueError("parsed is None (parse_request_node first)")

        if not state.target_user_ids:
            raise ValueError("target_user_ids is empty (select_targets_node first)")

        parsed = state.parsed
        target_ids = state.target_user_ids

        print("[STATE] topic =", parsed.topic)
        print("[STATE] target_user_ids count =", len(target_ids))

        llm = openai_chat_model()

        # DM 작성은 일단 tool 없이(추후 성향/리포트 tool 붙일 예정)
        tools = []

        tendency_context = get_tendency_profiles_context()

        agent = create_agent(
            model=llm,
            tools=tools,
            response_format=ComposeDM,  # ✅ Pydantic 강제
            system_prompt=(
                "너는 부트캠프 운영진을 위한 DM 작성 어시스턴트다.\n"
                "운영진이 그대로 복사해서 개인 DM으로 발송할 수 있게 작성해라.\n\n"
                f"[성향 분석 정보] {tendency_context}\n\n"
                "[규칙]\n"
                "- 한국어로 작성\n"
                "- 너무 길지 않게(3~6문장 권장)\n"
                "- 상대가 기분 나쁘지 않게, 명확하게 해야 할 행동이 보이게\n"
                "- 주제(topic)를 반영해서 안내\n"
                "- 성향 분석 정보를 반영해서 개인화\n"
                "- urgency가 high면 톤을 약간 더 단호하게\n"
                "- personality은 성향 분석 정보를 기반으로 개인의 성향에 따라 아래 중 하나로 선택:\n"
                "  friendly / formal / concise / detailed / encouraging\n"
                "- 최종 출력은 response_format 구조화 결과로만 생성한다\n"
                "- 제공된 내용 외에 추가 정보는 절대 넣지 않는다\n"
            ),
        )

        dm_results: List[ComposeDMResult] = []

        for idx, user_id in enumerate(target_ids):
            print(f"[LLM] compose_dm_node invoke ({idx+1}/{len(target_ids)}) user_id={user_id}")

            # user의 성향/이전 대화 내역 등을 반영하려면 여기에 추가 인자 전달
            user: User = get_user_by_id(user_id)

            user_content = (
                f"user_id: {user_id}\n"
                f"user_name: {user.name}\n"
                f"tendancy_code: {user.tendency_type_code}\n"
                f"topic: {parsed.topic}\n"
                f"urgency: {parsed.urgency}\n\n"
                f"사용자 요청 원문: {state.request_text}"
                "이 사용자에게 보낼 DM을 작성해줘."
            )

            result = agent.invoke({
                "messages": [{"role": "user", "content": user_content}]
            })

            structured: ComposeDMResult = result["structured_response"]
            print("[LLM] DM structured_response =", structured.model_dump())

            dm_results.append(structured)

        state.dm_messages = dm_results
        state.error = None

        print("[STATE] dm_messages count =", len(state.dm_messages))
        print("[NODE] compose_dm_node END")
        return state

    except Exception as e:
        print("[ERROR] compose_dm_node failed")
        print(e)
        state.error = f"compose_dm_node failed: {e}"
        state.dm_messages = []
        return state
