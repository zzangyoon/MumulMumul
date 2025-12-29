# app/services/send_dispatch/nodes/dispatch_and_log_node.py
import sys
from pathlib import Path

CURRENT_FILE = Path(__file__).resolve()
ROOT_DIR = CURRENT_FILE.parents[4]
sys.path.append(str(ROOT_DIR))

from app.services.send_dispatch.schemas import MessagingAgentState
from app.tools.dispatch_tools import dispatch_stub, dispatch_websocket_dm, dispatch_websocket_notice


async def dispatch_and_log_node(state: MessagingAgentState) -> MessagingAgentState:
    print("\n==============================")
    print("[NODE] dispatch_and_log_node START")

    try:
        if not state.target_user_ids:
            raise ValueError("target_user_ids is empty")

        parsed = state.parsed
        results = []

        # 공지 전송
        if parsed.message_type == "notice":
            print("[DISPATCH] notice mode")
            camp_id = state.camp_id
            target_user_ids = state.target_user_ids
            result = await dispatch_websocket_notice.ainvoke({"camp_id": camp_id, "target_user_ids": target_user_ids, "title": state.notice_message.title,  "message_text": state.notice_message.message_text, "sender_id": 1, "is_need_confirmation": True})
            results.append(result)

        # DM 전송
        elif parsed.message_type == "dm":
            print("[DISPATCH] dm mode")
            if not state.dm_messages:
                raise ValueError("dm_messages is empty")

            for dm in state.dm_messages:
                result = await dispatch_websocket_dm.ainvoke({"user_id": dm.user_id, "message_text": dm.message_text, "camp_id": state.camp_id, "sender_id": 1, "is_need_confirmation": False})
                results.append(result)

        else:
            raise ValueError(f"unsupported message_type: {parsed.message_type}")

        state.dispatch_result = {
            "attempted": len(results),
            "sent": len(results),
            "failed": 0,
            "channel": parsed.delivery_channel,
        }

        print("[STATE] dispatch_result =", state.dispatch_result)
        print("[NODE] dispatch_and_log_node END")
        return state

    except Exception as e:
        print("[ERROR] dispatch_and_log_node failed")
        print(e)
        state.error = f"dispatch_and_log_node failed: {e}"
        return state
