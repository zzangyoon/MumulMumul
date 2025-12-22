# app/services/send_notice/graph.py
import sys
from pathlib import Path

CURRENT_FILE = Path(__file__).resolve()
ROOT_DIR = CURRENT_FILE.parents[3]  # .../app/services/send_notice/graph.py 기준
sys.path.append(str(ROOT_DIR))

import asyncio
from datetime import datetime

from langgraph.graph import StateGraph, END

from app.services.send_notice.schemas import (
    MessagingAgentState,
    ParsedMessagingRequest,
)

# --- Nodes ---
from app.services.send_notice.nodes.parse_request_node import parse_request_node
from app.services.send_notice.nodes.select_targets_node import select_targets_node

# 라우터: message_type -> 다음 노드 key 반환(str)
from app.services.send_notice.nodes.compose_router_node import compose_router_node

# 메시지 생성 노드들
from app.services.send_notice.nodes.compose_notice_node import compose_notice_node
from app.services.send_notice.nodes.compose_dm_node import compose_dm_node

# dispatch (websocket 지원하려면 async 권장)
from app.services.send_notice.nodes.dispatch_and_log_node import dispatch_and_log_node


def build_send_notice_graph():
    """
    Flow:
      parse_request
        -> select_targets
        -> compose_messages_router (conditional)
            -> compose_notice_node
            -> compose_dm_node
        -> dispatch_and_log
        -> END
    """
    g = StateGraph(MessagingAgentState)

    # 1) 노드 등록
    g.add_node("parse_request_node", parse_request_node)
    g.add_node("select_targets_node", select_targets_node)

    g.add_node("compose_notice_node", compose_notice_node)
    g.add_node("compose_dm_node", compose_dm_node)

    # dispatch가 async 함수면 그대로 add_node 가능 (LangGraph는 async 지원)
    g.add_node("dispatch_and_log_node", dispatch_and_log_node)

    # 2) 시작점
    g.set_entry_point("parse_request_node")

    # 3) 직렬 연결
    g.add_edge("parse_request_node", "select_targets_node")
    g.add_edge("compose_notice_node", "dispatch_and_log_node")
    g.add_edge("compose_dm_node", "dispatch_and_log_node")
    g.add_edge("dispatch_and_log_node", END)

    # 4) 조건 분기 (라우터가 "compose_notice_node" / "compose_dm_node" 반환)
    g.add_conditional_edges(
        "select_targets_node",
        compose_router_node,
        {
            "compose_notice_node": "compose_notice_node",
            "compose_dm_node": "compose_dm_node",
        },
    )

    # 5) 합류
    g.add_edge("compose_notice_node", "dispatch_and_log_node")
    g.add_edge("compose_dm_node", "dispatch_and_log_node")

    # 6) 종료
    g.add_edge("dispatch_and_log_node", END)

    return g.compile()


# ------------------------------------------------------------
# Test (하단 테스트 코드)
# ------------------------------------------------------------
if __name__ == "__main__":
    app = build_send_notice_graph()

    # ✅ 테스트 1) notice (camp_all)
    test_state_notice = MessagingAgentState(
        request_text="머물머물 캠프로 긴급 공지를 보내줘. 내용은 훈련장려금(5차) 확인 안내야.",
        current_time=datetime.now(),
        # MVP에서 parse_request_node가 채우는 값이지만,
        # 빠른 테스트 위해 parsed를 미리 넣고 싶으면 아래처럼 넣어도 됨
        parsed=ParsedMessagingRequest(
            message_type="notice",
            target_scope="camp_all",
            camp_name="머물머물 캠프",
            topic="훈련장려금(5차) 확인 안내",
            delivery_channel="stub",   # "websocket"으로 바꾸면 ws 연결된 유저에게만 전송됨
            urgency="high",
            language="ko",
        )
    )

    async def run_tests():
        print("\n\n==============================")
        print("TEST 1) NOTICE")
        print("==============================")

        # dispatch_and_log_node가 async라면 ainvoke로 실행
        result_state_1 = await app.ainvoke(test_state_notice)
        print("\n[RESULT] camp_id =", getattr(result_state_1, "camp_id", None))
        print("[RESULT] target_user_ids count =", len(getattr(result_state_1, "target_user_ids", []) or []))
        print("[RESULT] message_text =", getattr(result_state_1, "message_text", None))
        print("[RESULT] dispatch_result =", getattr(result_state_1, "dispatch_result", None))
        print("[RESULT] error =", getattr(result_state_1, "error", None))

        # ✅ 테스트 2) dm (user_list 예시)
        # print("\n\n==============================")
        # print("TEST 2) DM")
        # print("==============================")

        # test_state_dm = MessagingAgentState(
        #     request_text="머물머물 캠프에서 김해찬, 윤여민에게 훈련장려금 확인 DM 보내줘",
        #     current_time=datetime.now(),
        #     parsed=ParsedMessagingRequest(
        #         message_type="dm",
        #         target_scope="user_list",
        #         camp_name="머물머물 캠프",
        #         user_names=["김해찬", "윤여민"],
        #         topic="훈련장려금(5차) 확인 안내",
        #         delivery_channel="stub",
        #         urgency="normal",
        #         language="ko",
        #     )
        # )

        # result_state_2 = await app.ainvoke(test_state_dm)
        # print("\n[RESULT] camp_id =", getattr(result_state_2, "camp_id", None))
        # print("[RESULT] target_user_ids =", getattr(result_state_2, "target_user_ids", None))
        # print("[RESULT] dm_messages count =", len(getattr(result_state_2, "dm_messages", []) or []))
        # print("[RESULT] dispatch_result =", getattr(result_state_2, "dispatch_result", None))
        # print("[RESULT] error =", getattr(result_state_2, "error", None))

    asyncio.run(run_tests())
