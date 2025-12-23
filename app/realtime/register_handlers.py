from app.realtime.ws_manager import ws_manager

# learning
from app.realtime.handlers.learning import start_chat as learning_start
from app.realtime.handlers.learning import query as learning_query
from app.realtime.handlers.learning import end_chat as learning_end

# meeting
from app.realtime.handlers.meeting import start_chat as meeting_start
from app.realtime.handlers.meeting import query as meeting_query
from app.realtime.handlers.meeting import end_chat as meeting_end

# dispatch
from app.realtime.handlers.dispatch import ack as dispatch_ack
from app.realtime.handlers.dispatch import ping as ping
# (push는 send_to_user로 서버가 직접 발송하므로 수신 이벤트는 ack 정도만)

def register_all():
    # system
    ws_manager.register("system", "register", ws_manager.handle_register)

    # learning
    ws_manager.register("learning", "start_chat", learning_start)
    ws_manager.register("learning", "query", learning_query)
    ws_manager.register("learning", "end_chat", learning_end)

    # meeting
    ws_manager.register("meeting", "start_chat", meeting_start)
    ws_manager.register("meeting", "query", meeting_query)
    ws_manager.register("meeting", "end_chat", meeting_end)

    # dispatch
    ws_manager.register("dispatch", "ack", dispatch_ack)
    ws_manager.register("dispatch", "ping", ping)
