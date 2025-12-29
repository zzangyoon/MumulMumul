# app/services/send_dispatch/runtime.py
from langgraph.checkpoint.memory import MemorySaver
from app.services.send_dispatch.build_graph import build_send_dispatch_graph, build_preview_dispatch_graph

checkpointer = MemorySaver()

# compile에 checkpointer를 넣어야 interrupt/resume가 됨
app = build_preview_dispatch_graph().with_config({"recursion_limit": 100}).compile(
    checkpointer=checkpointer
)
