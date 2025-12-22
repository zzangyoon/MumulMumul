# app/services/send_notice/nodes/dispatch_and_log_node.py
import sys
from pathlib import Path

CURRENT_FILE = Path(__file__).resolve()
ROOT_DIR = CURRENT_FILE.parents[4]
sys.path.append(str(ROOT_DIR))

from app.services.send_notice.schemas import MessagingAgentState
from app.tools.dispatch_tools import dispatch_stub


def dispatch_and_log_node(state: MessagingAgentState) -> MessagingAgentState:
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
            for user_id in state.target_user_ids:
                result = dispatch_stub.invoke({"user_id": user_id, "message_text": state.notice_message.message_text})
                results.append(result)

        # DM 전송
        elif parsed.message_type == "dm":
            print("[DISPATCH] dm mode")
            if not state.dm_messages:
                raise ValueError("dm_messages is empty")

            for dm in state.dm_messages:
                result = dispatch_stub.invoke({"user_id": user_id, "message_text": dm.message_text})
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
