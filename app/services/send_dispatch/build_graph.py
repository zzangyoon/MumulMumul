# app/services/send_dispatch/graph.py
from functools import lru_cache
import sys
from pathlib import Path

CURRENT_FILE = Path(__file__).resolve()
ROOT_DIR = CURRENT_FILE.parents[3]  # .../app/services/send_dispatch/graph.py 기준
sys.path.append(str(ROOT_DIR))

import asyncio
from datetime import datetime

from langgraph.graph import StateGraph, END

from app.services.send_dispatch.schemas import (
    MessagingAgentState,
    ParsedMessagingRequest,
)

# --- Nodes ---
from app.services.send_dispatch.nodes.parse_request_node import parse_request_node
from app.services.send_dispatch.nodes.execute_query_plans_node import execute_query_plans_node
from app.services.send_dispatch.nodes.select_targets_node import select_targets_node

# 라우터: message_type -> 다음 노드 key 반환(str)
from app.services.send_dispatch.nodes.compose_router_node import compose_router_node

# 메시지 생성 노드들
from app.services.send_dispatch.nodes.compose_notice_node import compose_notice_node
from app.services.send_dispatch.nodes.compose_dm_node import compose_dm_node

# approve (preview)
from app.services.send_dispatch.nodes.approve_before_dispatch_node import approve_before_dispatch_node

# dispatch
from app.services.send_dispatch.nodes.dispatch_and_log_node import dispatch_and_log_node


@lru_cache()
def build_send_dispatch_graph():
    """
    (기존)
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

    g.add_node("parse_request_node", parse_request_node)
    g.add_node("select_targets_node", select_targets_node)

    g.add_node("compose_notice_node", compose_notice_node)
    g.add_node("compose_dm_node", compose_dm_node)

    g.add_node("dispatch_and_log_node", dispatch_and_log_node)

    g.set_entry_point("parse_request_node")

    g.add_edge("parse_request_node", "select_targets_node")

    g.add_conditional_edges(
        "select_targets_node",
        compose_router_node,
        {
            "compose_notice_node": "compose_notice_node",
            "compose_dm_node": "compose_dm_node",
        },
    )

    g.add_edge("compose_notice_node", "dispatch_and_log_node")
    g.add_edge("compose_dm_node", "dispatch_and_log_node")
    g.add_edge("dispatch_and_log_node", END)

    return g.compile()


def build_preview_dispatch_graph():
    """
    (기존 preview)
    Flow:
      parse_request
        -> select_targets
        -> compose_messages_router (conditional)
            -> compose_notice_node
            -> compose_dm_node
        -> approve_before_dispatch_node
        -> dispatch_and_log
        -> END
    """
    g = StateGraph(MessagingAgentState)

    g.add_node("parse_request_node", parse_request_node)
    g.add_node("select_targets_node", select_targets_node)

    g.add_node("compose_notice_node", compose_notice_node)
    g.add_node("compose_dm_node", compose_dm_node)

    g.add_node("approve_before_dispatch_node", approve_before_dispatch_node)
    g.add_node("dispatch_and_log_node", dispatch_and_log_node)

    g.set_entry_point("parse_request_node")

    g.add_edge("parse_request_node", "select_targets_node")

    g.add_conditional_edges(
        "select_targets_node",
        compose_router_node,
        {
            "compose_notice_node": "compose_notice_node",
            "compose_dm_node": "compose_dm_node",
        },
    )

    # compose -> approve -> dispatch
    g.add_edge("compose_notice_node", "approve_before_dispatch_node")
    g.add_edge("compose_dm_node", "approve_before_dispatch_node")
    g.add_edge("approve_before_dispatch_node", "dispatch_and_log_node")
    g.add_edge("dispatch_and_log_node", END)

    return g


@lru_cache()
def build_send_dispatch_graph_with_query_plans():
    """
    (신규) parse_request_node 에서 나온 query_plans 를 먼저 실행한 뒤,
    select_targets_node 로 넘어가는 그래프.

    Flow:
      parse_request
        -> execute_query_plans
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
    g.add_node("execute_query_plans_node", execute_query_plans_node)
    g.add_node("select_targets_node", select_targets_node)

    g.add_node("compose_notice_node", compose_notice_node)
    g.add_node("compose_dm_node", compose_dm_node)

    g.add_node("dispatch_and_log_node", dispatch_and_log_node)

    # 2) 시작점
    g.set_entry_point("parse_request_node")

    # 3) 직렬 연결: parse -> execute_query_plans -> select_targets
    g.add_edge("parse_request_node", "execute_query_plans_node")
    g.add_edge("execute_query_plans_node", "select_targets_node")

    # 4) 조건 분기
    g.add_conditional_edges(
        "select_targets_node",
        compose_router_node,
        {
            "compose_notice_node": "compose_notice_node",
            "compose_dm_node": "compose_dm_node",
        },
    )

    # 5) 합류 및 종료
    g.add_edge("compose_notice_node", "dispatch_and_log_node")
    g.add_edge("compose_dm_node", "dispatch_and_log_node")
    g.add_edge("dispatch_and_log_node", END)

    return g.compile()


# ------------------------------------------------------------
# Test (하단 테스트 코드)
# ------------------------------------------------------------
if __name__ == "__main__":
    # ✅ 기존 그래프 / preview 그래프 / query_plans 포함 그래프 중 원하는 걸 골라서 테스트
    app = build_send_dispatch_graph_with_query_plans()

    # ✅ 테스트 1) NOTICE (camp_all)
    # - parse_request_node 가 query_plans를 생성할 수 있게 parsed를 미리 넣지 않는 방식 권장
    test_state_notice = MessagingAgentState(
        request_text="머물머물 캠프로 긴급 공지를 보내줘. 내용은 훈련장려금(5차) 확인 안내야.",
        current_time=datetime.now(),
        # 아래처럼 parsed를 미리 넣어도 되지만,
        # 이 경우 parse_request_node가 이미 채워진 걸 덮어쓸 수 있음(구현에 따라).
        # 그래서 query_plans 테스트 목적이면 보통 parsed는 비워두는 게 안전함.
        # parsed=ParsedMessagingRequest(...),
    )

    # ✅ 테스트 2) DM (지각자 타겟)
    test_state_dm_late = MessagingAgentState(
        request_text="안녕, 머물머물 캠프의 모든 지각자 또는 결석자들에게 QR코드 알림에 대한 DM을 보내줘.",
        current_time=datetime.now(),
    )

    async def run_tests():
        # print("\n\n==============================")
        # print("TEST 1) NOTICE (with query_plans)")
        # print("==============================")
        # result_state_1 = await app.ainvoke(test_state_notice)
        # print("\n[RESULT] camp_id =", getattr(result_state_1, "camp_id", None))
        # print("[RESULT] target_user_ids count =", len(getattr(result_state_1, "target_user_ids", []) or []))
        # print("[RESULT] query_results keys =", list(getattr(result_state_1, "query_results", {}) or {}))
        # print("[RESULT] dispatch_result =", getattr(result_state_1, "dispatch_result", None))
        # print("[RESULT] error =", getattr(result_state_1, "error", None))

        print("\n\n==============================")
        print("TEST 2) DM LATE (with query_plans)")
        print("==============================")
        result_state_2 = await app.ainvoke(test_state_dm_late)
        print("\n[RESULT] camp_id =", getattr(result_state_2, "camp_id", None))
        print("[RESULT] target_user_ids count =", len(getattr(result_state_2, "target_user_ids", []) or []))
        print("[RESULT] query_results keys =", list(getattr(result_state_2, "query_results", {}) or {}))
        print("[RESULT] dm_messages count =", len(getattr(result_state_2, "dm_messages", []) or []))
        print("[RESULT] dispatch_result =", getattr(result_state_2, "dispatch_result", None))
        print("[RESULT] error =", getattr(result_state_2, "error", None))

    asyncio.run(run_tests())
