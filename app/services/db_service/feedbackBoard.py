# app/services/db_service/feedbackBoard.py
from datetime import datetime

from requests import Session
from app.core.mongodb import mongo_db

from app.core.schemas import Camp
from app.services.db_service.camp import get_camp_by_user_id

from app.services.feedbackBoard.schemas import FeedbackBoardPost

feedback_col = mongo_db["feedback_board_posts"]

def add_feedback_post(db: Session, user_id: int, raw_text: str) -> FeedbackBoardPost:
    """
    새로운 피드백 게시글을 생성하여 MongoDB에 저장합니다.
    """
    camp: Camp = get_camp_by_user_id(db, user_id)

    new_post = FeedbackBoardPost(
        camp_id=camp.camp_id if camp else None,
        author_id=user_id,
        raw_text=raw_text,
        created_at=datetime.utcnow(),
    )
    result = feedback_col.insert_one(new_post.model_dump())
    new_post.id = result.inserted_id
    return new_post

# 일정 기간의 피드백 게시글을 가져오는 함수
def get_feedback_posts_by_date_range(camp_id: id, start_date: datetime, end_date: datetime) -> list[FeedbackBoardPost]:
    """
    특정 캠프의 지정된 날짜 범위 내의 피드백 게시글을 MongoDB에서 조회합니다.
    """
    query = {
        "camp_id": camp_id,
        "created_at": {
            "$gte": start_date,
            "$lte": end_date
        }
    }
    posts_cursor = feedback_col.find(query)
    posts = [FeedbackBoardPost(**post) for post in posts_cursor]
    return posts