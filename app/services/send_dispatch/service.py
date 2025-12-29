# ------------------------------------------------------------
# 7) F. 공지 및 DM 자동화 레이어
#   - 여러 요청(예시 - 오늘 지각자들에게 DM 보내줘/학습 리포트를 기반으로 연습 문제 만들어서 보내줘/00캠프 학생들에게 00에 대한 공지 보내줘)을 기반으로
#   -> DM 대상자 선정
#   -> 메시지 생성 
#   -> dispatch 로그 저장
# ------------------------------------------------------------
from datetime import datetime, timezone
from typing import Any
from requests import Session

from langgraph.types import Command

from app.services.send_dispatch.build_graph import build_preview_dispatch_graph, build_send_dispatch_graph
from app.services.send_dispatch.schemas import MessagingAgentState

async def plan_and_dispatch_dm(
    db: Session,
    request_data: str,
    sender_id: int = 1,
    config: dict[str, Any] | None = None,
):
    """공지 및 DM 자동화 서비스"""

    # graph 기반으로 메시지 생성 및 대상자 선정 로직 구현 필요
    graph = build_send_dispatch_graph()

    
    state = MessagingAgentState(
        sender_id=sender_id,
        request_text=request_data,
        current_time=datetime.now(timezone.utc),
    )
    
    # dispatch_and_log_node가 async라면 ainvoke로 실행
    result = await graph.ainvoke(state, config=config)
    print("\n[RESULT] camp_id =", getattr(result, "camp_id", None))
    print("[RESULT] target_user_ids count =", len(getattr(result, "target_user_ids", []) or []))
    print("[RESULT] message_text =", getattr(result, "message_text", None))
    print("[RESULT] dispatch_result =", getattr(result, "dispatch_result", None))
    print("[RESULT] error =", getattr(result, "error", None))

    return result

async def preview_dispatch(
    db: Session,
    request_data: str,
    sender_id: int = 1,
    config: dict[str, Any] | None = None,
):
    """운영진이 dispatch 미리보기하는 함수"""
    # graph 기반으로 메시지 생성 및 대상자 선정 로직 구현 필요
    graph = build_preview_dispatch_graph()
    
    state = MessagingAgentState(
        sender_id=sender_id,
        request_text=request_data,
        current_time=datetime.now(),
    )
    
    result = await graph.ainvoke(state, config=config)
    
    return result

async def confirm_dispatch(
    db: Session,
    thread_id: str,
    approved: bool,
    edited_text: str | None = None,
    config: dict[str, Any] | None = None,
):
    """운영진이 미리보기 후 dispatch 확정하는 함수"""

    # graph 기반으로 메시지 생성 및 대상자 선정 로직 구현 필요
    graph = build_preview_dispatch_graph()
    cmd = Command(resume={"approved": approved, "edited_text": edited_text})
   
    result = await graph.ainvoke(cmd, config=config})
    
    return result