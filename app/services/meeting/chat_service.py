from datetime import datetime
from typing import List, Dict
from app.core.logger import setup_logger
from app.core.mongodb import get_mongo_db
from app.core.timezone import timestamp_to_datetime, format_datetime

logger = setup_logger(__name__)

class ChatService:
    """채팅 메시지 처리 서비스"""

    def __init__(self):
        self.mongo_db = get_mongo_db()
        self.collection = self.mongo_db["team_chat_messages"]

    def get_meeting_chat_messages(
        self,
        room_id: str,
        start_timestamp: int,
        end_timestamp: int
    ) -> List[Dict]:
        """
        회의 구간의 채팅 메시지 조회
        
        Args:
            room_id: 채팅방 ID (meeting.chat_room_id)
            start_timestamp: 회의 시작 시간 (ms)
            end_timestamp: 회의 종료 시간 (ms)
        
        Returns:
            채팅 메시지 리스트 (시간순 정렬)
        """
        try:
            logger.info(
                f"채팅 메시지 조회\n"
                f"  room_id: {room_id}\n"
                f"  start: {start_timestamp}\n"
                f"  end: {end_timestamp}"
            )

            start_dt = timestamp_to_datetime(start_timestamp)
            end_dt = timestamp_to_datetime(end_timestamp)
            
            start_iso = format_datetime(start_dt, "%Y-%m-%dT%H:%M:%S.%f")
            end_iso = format_datetime(end_dt, "%Y-%m-%dT%H:%M:%S.%f")

            logger.info(
                f"start_iso ::: {start_iso}\n"
                f"end_iso ::: {end_iso}\n"
            )

            # MongoDB 쿼리
            messages = self.collection.find({
                "roomId" : room_id,
                "type" : "team",
                "createdAt" : {
                    "$gte" : start_iso,
                    "$lte" : end_iso
                }
            }).sort("createdAt", 1)    # 시간순 정렬

            # 리스트 변환
            result = []
            for msg in messages:
                # created_at을 timestamp로 변환
                created_at = datetime.fromisoformat(msg["createdAt"])
                created_timestamp = int(created_at.timestamp() * 1000)

                result.append({
                    "user_id" : msg["userId"],
                    "user_name" : msg["userName"],
                    "message" : msg["message"],
                    "created_at" : msg["createdAt"],
                    "timestamp_ms" : created_timestamp
                })
            logger.info(f"채팅 메시지 {len(result)}개 조회 완료")
            return result

        except Exception as e:
            logger.error(f"채팅 메시지 조회 실패: {e}", exc_info=True)
            return []