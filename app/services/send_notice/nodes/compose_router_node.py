# app/services/send_notice/nodes/compose_messages_router_node.py
from app.services.send_notice.schemas import MessagingAgentState

def compose_router_node(state: MessagingAgentState) -> str:
    print("\n==============================")
    print("[NODE] compose_router_node START")

    if not state.parsed:
        raise ValueError("parsed is None")

    message_type = state.parsed.message_type
    print("[STATE] message_type =", message_type)

    if message_type == "notice":
        next_node = "compose_notice_node"
    elif message_type == "dm":
        next_node = "compose_dm_node"
    else:
        raise ValueError(f"unsupported message_type: {message_type}")

    print("[ROUTER] next_node =", next_node)
    print("[NODE] compose_router_node END")

    return next_node
