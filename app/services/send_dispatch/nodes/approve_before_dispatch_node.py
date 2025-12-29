from langgraph.types import interrupt

def approve_before_dispatch_node(state):
    """
    dispatch 직전에 멈추고, 클라이언트가 승인/취소를 결정하게 한다.
    resume로 받은 값은 interrupt()의 반환값이 된다.
    """

    preview = {
        "message_type": state.parsed.message_type,         # "notice" | "dm"
        "camp_id": state.camp_id,
        "target_user_ids": state.target_user_ids,
        "target_count": len(state.target_user_ids or []),
        "title": getattr(state, "title", None),            # notice 제목(있으면)
        "text": getattr(state, "message_text", None),      # 최종 본문
        "delivery_channel": state.parsed.delivery_channel,
        "need_confirmation": getattr(state, "is_need_confirmation", False),
    }

    decision = interrupt(preview)
    # decision 예시: {"approved": True} or {"approved": False}

    state.approval = decision
    return state
