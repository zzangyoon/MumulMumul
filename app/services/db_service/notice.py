# app/services/db_service/notice.py

from datetime import datetime
from sqlalchemy.orm import Session
from app.core.schemas import NoticeLog, NoticeConfirmation


def send_dm(
    db: Session,
    camp_id: int,
    recipient_id: int,
    message: str,
    sender_id: int | None = None,
    is_need_confirmation: bool = False,
) -> int:
    """
    DM 저장(NoticeLog) + (선택) 확인 테이블 생성
    return: notice_id
    """
    notice = NoticeLog(
        camp_id=camp_id,
        Recipient_id=recipient_id,
        Sender_id=sender_id,
        message=message,
        is_need_confirmation=is_need_confirmation,
    )
    db.add(notice)
    db.commit()
    db.refresh(notice)

    if is_need_confirmation:
        conf = NoticeConfirmation(
            notice_id=notice.id,
            camp_id=camp_id,
            user_id=recipient_id,
            is_confirmed=False,
            created_at=datetime.utcnow(),
        )
        db.add(conf)
        db.commit()

    return notice.id


def confirm_notice(
    db: Session,
    camp_id: int,
    user_id: int,
    notice_id: int,
) -> bool:
    """
    유저가 notice 확인 처리
    """
    row = (
        db.query(NoticeConfirmation)
        .filter(
            NoticeConfirmation.notice_id == notice_id,
            NoticeConfirmation.camp_id == camp_id,
            NoticeConfirmation.user_id == user_id,
        )
        .first()
    )
    if not row:
        return False

    row.is_confirmed = True
    row.confirmed_at = datetime.utcnow()
    db.commit()
    return True
