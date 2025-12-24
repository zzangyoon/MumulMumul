# ------------------------------------------------------------
# 7) F. 공지 및 DM 자동화 레이어
#   - 여러 요청(예시 - 오늘 지각자들에게 DM 보내줘/학습 리포트를 기반으로 연습 문제 만들어서 보내줘/00캠프 학생들에게 00에 대한 공지 보내줘)을 기반으로
#   -> DM 대상자 선정
#   -> 메시지 생성 
#   -> dispatch 로그 저장
# ------------------------------------------------------------
import asyncio
import datetime
from typing import Any
from requests import Session

from app.services.send_dispatch.graph import build_send_dispatch_graph
from app.services.send_dispatch.schemas import MessagingAgentState

def plan_and_dispatch_dm(
    db: Session,
    request_data: str
):
    """공지 및 DM 자동화 서비스"""

    # graph 기반으로 메시지 생성 및 대상자 선정 로직 구현 필요
    graph = build_send_dispatch_graph()

    
    state = MessagingAgentState(
        request_text=request_data,
        current_time=datetime.now(),
    )
    
    async def run_tests():
        # dispatch_and_log_node가 async라면 ainvoke로 실행
        result_state_1 = await graph.ainvoke(state)
        print("\n[RESULT] camp_id =", getattr(result_state_1, "camp_id", None))
        print("[RESULT] target_user_ids count =", len(getattr(result_state_1, "target_user_ids", []) or []))
        print("[RESULT] message_text =", getattr(result_state_1, "message_text", None))
        print("[RESULT] dispatch_result =", getattr(result_state_1, "dispatch_result", None))
        print("[RESULT] error =", getattr(result_state_1, "error", None))

    asyncio.run(run_tests())

    return "Not implemented yet"
