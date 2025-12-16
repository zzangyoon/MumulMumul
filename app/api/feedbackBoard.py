# 익명 게시판에 업로드한 피드백을 처리하는 API
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List

from requests import Session
from app.core.db import get_db
from app.services.db_service.feedback_reports import get_weekly_report
from app.services.feedbackBoard.schemas import FeedbackBoardPost, FeedbackWeeklyReport
from app.services.db_service.feedbackBoard import add_feedback_post
from app.services.feedbackBoard.service import build_feedback_report

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
@router.get("/report/{camp_id}/{week_index}", response_model=FeedbackWeeklyReport | None)
async def get_feedback_report(camp_id: int, week_index: int, db: Session = Depends(get_db)):
    report: FeedbackWeeklyReport | None = get_weekly_report(
        camp_id=camp_id,
        week=week_index,
    )

    return report

# 리포트 생성하기
@router.post("/report/{camp_id}/{week_index}/build", response_model=FeedbackWeeklyReport)
async def build_feedback_report_endpoint(camp_id: int, week_index: int, db: Session = Depends(get_db)):

    build_feedback_report(
        db=db,
        camp_id=camp_id,
        week_index=week_index,
    )

    report: FeedbackWeeklyReport = get_weekly_report(
        camp_id=camp_id,
        week=week_index,
    )

    return report