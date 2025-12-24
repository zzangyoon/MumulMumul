# 운영진이 dispatch를 보낼 때 사용하는 API
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.core.db import get_db
from app.services.send_dispatch.service import plan_and_dispatch_dm
from app.tools.dispatch_tools import dispatch_websocket_notice, dispatch_websocket_dm

router = APIRouter()

class DispatchSendRequestPayload(BaseModel):
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

    # result = plan_and_dispatch_dm(db=db, request_data=payload.request_text)
    
    # 테스트로 "QR코드 출결을 꼭 확인해주세요!" 라는 요청을 보낸다고 가정
    # 테스트로 dispatch_websocket_dm 함수를 사용
    # user_id: int,
    # message_text: str,
    # camp_id: Optional[int] = None,
    # sender_id: Optional[int] = None,
    # is_need_confirmation: bool = False,
    result = await dispatch_websocket_dm.ainvoke({
        "user_id": 5,
        "message_text": payload.request_text,
        "camp_id": 1,
        "sender_id": 1,
        "is_need_confirmation": False,
    }
    )
    

    return {"status": "success", "detail": result}