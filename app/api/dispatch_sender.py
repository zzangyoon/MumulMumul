# 운영진이 dispatch를 보낼 때 사용하는 API
import asyncio
from datetime import datetime
import json
import uuid
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.core.db import get_db
from app.services.send_dispatch.build_graph import build_send_dispatch_graph
from app.services.send_dispatch.schemas import MessagingAgentState
from app.services.send_dispatch.service import plan_and_dispatch_dm
from app.tools.dispatch_tools import dispatch_websocket_notice, dispatch_websocket_dm

router = APIRouter()

class DispatchSendRequestPayload(BaseModel):
    user_id: int
    request_text: str
    
# plan_and_dispatch_dm 함수를 사용
@router.post("/send")
async def send_dispatch(
    payload: DispatchSendRequestPayload,
    db: Session = Depends(get_db),
):
    """
    운영진이 dispatch를 보낼 때 사용하는 API
    """

    result = await plan_and_dispatch_dm(db=db, request_data=payload.request_text, sender_id=payload.user_id)
    
    # 테스트로 dispatch_websocket_dm 함수를 사용
    # user_id: int,
    # message_text: str,
    # camp_id: Optional[int] = None,
    # sender_id: Optional[int] = None,
    # is_need_confirmation: bool = False,
    # result = await dispatch_websocket_dm.ainvoke({
    #     "user_id": 5,
    #     "message_text": payload.request_text,
    #     "camp_id": 1,
    #     "sender_id": 1,
    #     "is_need_confirmation": False,
    # }
    # )
    
    return {"status": "success", "detail": result}


@router.post("/preview")
async def preview_dispatch(payload: DispatchSendRequestPayload, db=Depends(get_db)):
    thread_id = payload.thread_id or f"dispatch-{uuid.uuid4()}"

    config = {"configurable": {"thread_id": thread_id}}
    state = MessagingAgentState(request_text=payload.request_text, current_time=datetime.now())

    # result = await app.ainvoke(state, config=config)
    result = await preview_dispatch(
        db=db, 
        request_data=payload.request_text, 
        sender_id=payload.user_id, 
        config=config)

    # interrupt에 걸리면 result 안에 __interrupt__가 포함됨 :contentReference[oaicite:5]{index=5}
    preview = result.get("__interrupt__")
    return {"thread_id": thread_id, "preview": preview}

class ConfirmPayload(BaseModel):
    thread_id: str
    approved: bool
    edited_text: str | None = None

@router.post("/confirm")
async def confirm_dispatch(payload: ConfirmPayload, db=Depends(get_db)):
    config = {"configurable": {"thread_id": payload.thread_id}}
    result = await confirm_dispatch(
        db=db,
        thread_id=payload.thread_id,
        approved=payload.approved,
        edited_text=payload.edited_text,
        config=config
    )
    return {"status": "done", "detail": result}


# 중간 결과를 스트리밍으로 보내주는 API
@router.post("/send_stream")
async def send_dispatch_stream(payload: DispatchSendRequestPayload, db: Session = Depends(get_db)):
    async def event_gen():
        def emit(step: str, detail: dict | None = None):
            data = {"ts": datetime.utcnow().isoformat(), "step": step, "detail": detail or {}}
            return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

        yield emit("start")

        # state에 progress 콜백을 심어서 노드들이 계속 yield하도록
        state = MessagingAgentState(
            request_text=payload.request_text,
            current_time=datetime.now(),
            requester_user_id=getattr(payload, "user_id", None),  # 있으면 저장
        )

        async def progress_hook(step: str, detail: dict | None = None):
            # StreamingResponse에서 async yield를 직접 못 하므로
            # 큐로 넘기는 방식 권장 (아래가 더 안전)
            pass

        q: asyncio.Queue[str] = asyncio.Queue()

        async def progress(step: str, detail: dict | None = None):
            await q.put(emit(step, detail))

        state.progress = progress  # state에 콜백 심기

        task = asyncio.create_task(app.ainvoke(state))

        while True:
            if task.done() and q.empty():
                break
            try:
                msg = await asyncio.wait_for(q.get(), timeout=0.3)
                yield msg
            except asyncio.TimeoutError:
                continue

        result_state = task.result()
        yield emit("done", {"result": result_state.model_dump()})

    return StreamingResponse(event_gen(), media_type="text/event-stream")