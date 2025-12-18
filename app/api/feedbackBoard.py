# 익명 게시판에 업로드한 피드백을 처리하는 API
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List

from requests import Session
from app.core.db import get_db
from app.services.db_service.feedback_reports import get_weekly_report
from app.services.feedbackBoard.schemas import FeedbackBoardPost, FeedbackWeeklyReport, WeeklyKeyTopic, WeeklyOpsAction, WeeklyStats, WeeklyWordcloud
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

class FeedbackReportlog(BaseModel):
    post_id: str
    camp_id: int
    user_id: int
    author_id: int
    raw_text: str
    created_at: datetime
    severity: str | None
    clean_text: str | None
    is_toxic: bool | None
    category: str | None
    sub_category: str | None
    parent_post_id: str | None

class FeedbackReportResponse(BaseModel):
    camp_id: int
    week: int
    created_at: datetime
    weekly_summary: str
    key_topics: List[WeeklyKeyTopic]
    ops_actions: List[WeeklyOpsAction]
    stats: WeeklyStats
    wordcloud: WeeklyWordcloud
    logs: List[dict]

# 리포트 가져오기
@router.get("/report/{camp_id}/{week_index}", response_model=FeedbackReportResponse | None)
async def get_feedback_report(camp_id: int, week_index: int, db: Session = Depends(get_db)):
    report: FeedbackWeeklyReport | None = get_weekly_report(
        camp_id=camp_id,
        week=week_index,
    )

    return {
        "camp_id": report.camp_id,
        "week": report.week,
        "created_at": report.created_at,
        "weekly_summary": report.week_summary,
        "key_topics": report.key_topics,
        "ops_actions": report.ops_actions,
        "stats": report.stats,
        "wordcloud": report.wordcloud,
        "logs": [{
            "post_id": log.post_id,
            "camp_id": log.camp_id,
            "raw_text": log.raw_text,
            "created_at": log.created_at,
            "user_id": log.author_id,
            "author_id": log.author_id,
            "severity": log.ai_analysis.severity if log.ai_analysis else None,
            "clean_text": log.ai_analysis.clean_text if log.ai_analysis else None,
            "is_toxic": log.ai_analysis.is_toxic if log.ai_analysis else None,
            "category": log.ai_analysis.category if log.ai_analysis else None,
            "sub_category": log.ai_analysis.sub_category if log.ai_analysis else None,
            "parent_post_id": log.ai_analysis.parent_post_id if log.ai_analysis else None,
        } for log in report.logs],
    }

# 리포트 생성하기
@router.post("/report/{camp_id}/{week_index}/build", response_model=FeedbackReportResponse)
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

    return {
        "camp_id": report.camp_id,
        "week": report.week,
        "created_at": report.created_at,
        "weekly_summary": report.week_summary,
        "key_topics": report.key_topics,
        "ops_actions": report.ops_actions,
        "stats": report.stats,
        "wordcloud": report.wordcloud,
        "logs": [{
            "post_id": log.post_id,
            "camp_id": log.camp_id,
            "user_id": log.author_id,
            "raw_text": log.raw_text,
            "created_at": log.created_at,
            "severity": log.ai_analysis.severity if log.ai_analysis else None,
            "clean_text": log.ai_analysis.clean_text if log.ai_analysis else None,
            "is_toxic": log.ai_analysis.is_toxic if log.ai_analysis else None,
            "category": log.ai_analysis.category if log.ai_analysis else None,
            "sub_category": log.ai_analysis.sub_category if log.ai_analysis else None,
            "parent_post_id": log.ai_analysis.parent_post_id if log.ai_analysis else None,
            "summary": log.ai_analysis.summary if log.ai_analysis else None,
        } for log in report.logs],
    }