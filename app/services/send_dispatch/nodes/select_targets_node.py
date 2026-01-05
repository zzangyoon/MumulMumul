# app/services/send_dispatch/nodes/select_targets_node.py
import sys
from pathlib import Path

# 이 파일 기준으로 프로젝트 루트 계산
CURRENT_FILE = Path(__file__).resolve()
ROOT_DIR = CURRENT_FILE.parents[4]   # .../MumulMumul
sys.path.append(str(ROOT_DIR))

from pydantic import BaseModel, Field
from typing import List
from langchain.agents import create_agent
from langchain_core.output_parsers import PydanticOutputParser

from app.core.models import openai_chat_model
from app.services.send_dispatch.schemas import (
    MessagingAgentState,
    ParsedMessagingRequest,
    SelectTargetsResult,
)

from app.tools.db_tools import (
    get_camp_id_by_name,
    get_user_ids_by_camp_id,
    resolve_user_ids_by_names,
)

def select_targets_node(state: MessagingAgentState) -> MessagingAgentState:
    print("\n==============================")
    print("[NODE] select_targets_node START")

    try:
        parsed = state.parsed
        if not parsed:
            raise ValueError("parsed is None")

        print("[STATE] parsed_request =", parsed.model_dump())

        # ✅ (추가) 이미 상위 노드(execute_query_plans_node 등)에서 타겟이 정해졌으면 덮어쓰지 않는다.
        # - 빈 리스트([])면 False라서 기존 로직 그대로 진행
        if getattr(state, "target_user_ids", None):
            print("[SELECT_TARGETS] Skip tool-based selection: target_user_ids already set")
            print("[STATE] existing camp_id =", getattr(state, "camp_id", None))
            print("[STATE] existing target_user_ids count =", len(state.target_user_ids))
            print("[STATE] existing target_user_ids =", state.target_user_ids)

            # camp_id가 비어있는데 parsed.camp_name이 있다면 최소한 camp_id만 보완 (선택)
            if not getattr(state, "camp_id", None) and getattr(parsed, "camp_name", None):
                try:
                    cid = get_camp_id_by_name.invoke({"camp_name": parsed.camp_name})
                    state.camp_id = cid
                    print("[SELECT_TARGETS] Filled camp_id from camp_name:", cid)
                except Exception as _:
                    # camp_id 보완은 best-effort (실패해도 타겟팅은 유지)
                    pass

            state.error = None
            print("[NODE] select_targets_node END (skip overwrite)")
            return state

        # 1. 모델 및 도구 설정
        llm = openai_chat_model()
        tools = [get_camp_id_by_name, get_user_ids_by_camp_id, resolve_user_ids_by_names]
        parser = PydanticOutputParser(pydantic_object=SelectTargetsResult)

        # 2. 에이전트 생성
        agent = create_agent(
            model=llm,
            tools=tools,
            system_prompt=(
                "너는 메시지 전송 대상자 선정 모듈이다.\n"
                "필요한 데이터는 반드시 tools를 호출해 얻어라.\n\n"
                "규칙:\n"
                "- target_scope == 'camp_all'이면 camp_name으로 camp_id 조회 → 해당 camp 전체 user_ids 조회\n"
                "- target_scope == 'user_list'이면 camp_name으로 camp_id 조회 → user_names로 user_ids 조회\n\n"
                "최종 출력은 아래 스키마를 따르는 JSON만 출력해라.\n"
                "설명/문장/코드펜스(```)/추가 텍스트는 절대 금지.\n"
                f"{parser.get_format_instructions()}"
            ),
            response_format=SelectTargetsResult,
        )

        print("[LLM] select_targets_node invoke")

        # 3. 에이전트 호출
        out = agent.invoke(
            {
                "messages": [{
                    "role": "user",
                    "content": f"""
                        camp_name: {parsed.camp_name},
                        user_names: {parsed.user_names},
                        target_scope: {parsed.target_scope},
                        이 내용에 따라 최종 발송 대상의 camp_id와 user_id 목록을 반환해줘.
                    """
                }]
            }
        )

        print("[LLM] select_targets_node output")
        print("==============================")
        print("[OUTPUT] SelectTargetsResult:")
        print(out["messages"][-1].content)
        print("==============================")

        # 4. State 업데이트
        content = out["messages"][-1].content
        content_json = SelectTargetsResult.model_validate_json(content)
        state.camp_id = content_json.camp_id
        state.target_user_ids = content_json.target_user_ids
        state.error = None

        print("[STATE] camp_id =", state.camp_id)
        print("[STATE] target_user_ids count =", len(state.target_user_ids))
        print("[STATE] target_user_ids", state.target_user_ids)
        print("[NODE] select_targets_node END")

        return state

    except Exception as e:
        print("[ERROR] select_targets_node failed")
        print(e)
        state.error = f"select_targets_node failed: {e}"
        state.camp_id = None
        state.target_user_ids = []
        return state


if __name__ == "__main__":
    from datetime import datetime
    test_state = MessagingAgentState(
        request_text="머물머물 캠프로 긴급 공지를 보내고 싶어. 내용은 훈련장려금(5차) 확인에 대한 안내야.",
        current_time=datetime.now(),
        parsed=ParsedMessagingRequest(
            message_type="notice",
            target_scope="camp_all",
            camp_name="머물머물 캠프",
            topic="훈련장려금 확인"
        )
    )

    result_state = select_targets_node(test_state)
    print("Camp ID:", result_state.camp_id)
    print("Target User IDs:", result_state.target_user_ids)
    if result_state.error:
        print("Error:", result_state.error)
