# app/tools/dispatch_tools.py
from typing import Any, Dict, Optional, List
from datetime import datetime

from langchain_core.tools import tool

from app.realtime.ws_manager import ws_manager
from app.core.db import get_db
from app.core.schemas import Message, MessageRecipient


@tool
def dispatch_stub(user_id: int, message_text: str) -> Dict:
    """
    stub 전송: 실제로 보내지는 않지만 성공한 것처럼 처리
    """
    print(f"[STUB DISPATCH] user_id={user_id}")
    return {
        "user_id": user_id,
        "status": "sent",
        "channel": "stub",
    }


@tool
async def dispatch_websocket_dm(
    user_id: int,
    message_text: str,
    camp_id: Optional[int] = None,
    sender_id: Optional[int] = None,
    is_need_confirmation: bool = False,
) -> Dict[str, Any]:
    """
    WebSocket으로 개인 DM 전송 + DB 저장
    """
    db_gen = get_db()
    db = next(db_gen)
    try:
        # 1) Message 저장
        message = Message(
            message_type="dm",
            camp_id=camp_id,
            sender_id=sender_id,
            title=None,
            message_text=message_text,
            is_need_confirmation=is_need_confirmation,
        )
        db.add(message)
        db.flush()  # message.id 확보

        # 2) MessageRecipient 저장
        recipient = MessageRecipient(
            message_id=message.id,
            recipient_id=user_id,
            is_confirmed=False,
            confirmed_at=None,
        )
        db.add(recipient)

        db.commit()

        payload = {
                "messageId": message.id,
                "recipientId": user_id,
                "campId": camp_id,
                "senderId": sender_id,
                "title": None,
                "text": message_text,
                "createdAt": message.created_at.isoformat(),
                "needConfirmation": is_need_confirmation,
                "isConfirmed": False,
                "confirmedAt": None,
            }

        print(f"[WS DISPATCH] dm user_id={user_id} messageId={message.id}")
        return await ws_manager.send_to_user(user_id, domain="dispatch", event="dm", payload=payload)

    except Exception as e:
        db.rollback()
        print(f"[ERROR] dispatch_websocket_dm failed: {e}")
        raise
    finally:
        db.close()


@tool
async def dispatch_websocket_notice(
    camp_id: int,
    target_user_ids: List[int],
    title: str,
    message_text: str,
    sender_id: Optional[int] = None,
    is_need_confirmation: bool = True,
) -> Dict[str, Any]:
    """
    WebSocket으로 캠프 공지 전송 + DB 저장
    - Message 1개
    - MessageRecipient N개
    """
    db_gen = get_db()
    db = next(db_gen)
    try:
        # 1) Message 저장 (공지 원본 1개)
        message = Message(
            message_type="notice",
            camp_id=camp_id,
            sender_id=sender_id,
            title=title,
            message_text=message_text,
            is_need_confirmation=is_need_confirmation,
        )
        db.add(message)
        db.flush()  # message.id 확보

        # 2) MessageRecipient bulk 저장
        recipients = [
            MessageRecipient(
                message_id=message.id,
                recipient_id=user_id,
                is_confirmed=False,
                confirmed_at=None,
            )
            for user_id in target_user_ids
        ]
        db.add_all(recipients)

        db.commit()

        # 3) 각 유저에게 WS push
        for user_id in target_user_ids:
            payload = {
                    "messageId": message.id,
                    "recipientId": user_id,
                    "campId": camp_id,
                    "senderId": sender_id,
                    "title": title,
                    "text": message_text,
                    "createdAt": message.created_at.isoformat(),
                    "needConfirmation": is_need_confirmation,
                    "isConfirmed": False,
                    "confirmedAt": None,
                }
            await ws_manager.send_to_user(user_id, domain="dispatch", event="notice", payload=payload)

        print(
            f"[WS DISPATCH] notice camp_id={camp_id} "
            f"messageId={message.id} targets={len(target_user_ids)}"
        )

        return {
            "ok": True,
            "messageId": message.id,
            "targetCount": len(target_user_ids),
        }

    except Exception as e:
        db.rollback()
        print(f"[ERROR] dispatch_websocket_notice failed: {e}")
        raise
    finally:
        db.close()
