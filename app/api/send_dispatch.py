from typing import List, Literal, Optional
from pydantic import BaseModel
from datetime import timezone, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.core.db import get_db
from app.core.schemas import Message, MessageRecipient

router = APIRouter()

class DispatchPayload(BaseModel):
    messageId: int
    recipientId: int

    campId: Optional[int] = None
    senderId: Optional[int] = None

    title: Optional[str] = None
    text: str
    createdAt: datetime

    needConfirmation: bool
    isConfirmed: bool
    confirmedAt: Optional[datetime] = None

class DispatchEnvelope(BaseModel):
    domain: Literal["dispatch"] = "dispatch"
    event: Literal["notice", "dm"]
    payload: DispatchPayload

class DispatchHistoryResponse(BaseModel):
    items: List[DispatchEnvelope]

# -------------------------
# 1) History: 공지/DM 한 번에 내려주기
# -------------------------
@router.get("/history", response_model=DispatchHistoryResponse)
def get_dispatch_history(
    userId: int = Query(...),
    limit: int = Query(200, ge=1, le=1000),
    beforeMessageRecipientId: Optional[int] = Query(None, description="페이징용(옵션)"),
    db: Session = Depends(get_db),
):
    """
    - recipient 기준으로 최신순 히스토리 조회
    - MessageRecipient + Message JOIN
    - 결과는 WS로 보내는 것과 유사한 envelope 리스트로 반환
    """

    q = (
        db.query(MessageRecipient, Message)
        .join(Message, Message.id == MessageRecipient.message_id)
        .filter(MessageRecipient.recipient_id == userId)
    )

    # 옵션 페이징: 더 오래된 것(무한스크롤) 땡길 때 사용
    if beforeMessageRecipientId is not None:
        q = q.filter(MessageRecipient.id < beforeMessageRecipientId)

    rows = (
        q.order_by(desc(MessageRecipient.id))
        .limit(limit)
        .all()
    )

    items = []
    for mr, m in rows:
        items.append(
            DispatchEnvelope(
                event=m.message_type,  # "notice" or "dm"
                payload=DispatchPayload(
                    messageId=m.id,
                    recipientId=mr.recipient_id,
                    campId=m.camp_id,
                    senderId=m.sender_id,
                    title=m.title,
                    text=m.message_text,
                    createdAt=m.created_at,

                    needConfirmation=m.is_need_confirmation,
                    isConfirmed=mr.is_confirmed,
                    confirmedAt=(mr.confirmed_at if mr.confirmed_at else None),
                )
            )
        )

    return DispatchHistoryResponse(items=items)


# -------------------------
# 2) Confirm: 유저가 "확인" 눌렀을 때 메시지 1개 confirm
# -------------------------
class ConfirmMessageRequest(BaseModel):
    userId: int
    messageId: int

@router.post("/confirm")
def confirm_message(
    payload: ConfirmMessageRequest,
    db: Session = Depends(get_db),
):
    """
    유저가 특정 메시지(공지/DM)를 확인 버튼으로 확인 처리
    - MessageRecipient(message_id + recipient_id)만 업데이트
    """
    mr = (
        db.query(MessageRecipient)
        .filter(MessageRecipient.recipient_id == payload.userId)
        .filter(MessageRecipient.message_id == payload.messageId)
        .first()
    )
    if not mr:
        raise HTTPException(status_code=404, detail="MessageRecipient not found")

    # 이미 확인했으면 idempotent
    if not mr.is_confirmed:
        mr.is_confirmed = True
        mr.confirmed_at = datetime.now(timezone.utc)
        db.commit()

    return {"ok": True, "messageId": payload.messageId}