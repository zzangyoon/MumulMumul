# 익명 게시판에 업로드한 피드백을 처리하는 API
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List

from requests import Session
from app.core.db import get_db
from app.services.feedbackBoard.schemas import FeedbackBoardPost
from app.services.db_service.feedbackBoard import add_feedback_post

router = APIRouter()

class UploadFeedbackRequest(BaseModel):
    userId: int
    content: str

# 피드백 업로드 API
@router.post("/upload")
async def upload_feedback(payload: UploadFeedbackRequest, db: Session = Depends(get_db)):
    add_feedback_post(
        db,
        user_id=payload.userId,
        raw_text=payload.content
    )

    # 필수 필드 누락 / JSON 형식 오류 등 예외 처리
    if not payload.userId or not payload.content:
        return HTTPException(status_code=400, detail={
            "errorCode": "INVALID_FEEDBACK_PAYLOAD",
            "message": "Feedback 데이터가 올바르지 않습니다."
        })


    return HTTPException(status_code=200, detail={"message": "피드백이 성공적으로 업로드되었습니다."})

# 리포트 가져오기
# 리포트 생성하기