# app/services/db_service/feedback_reports.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from app.core.mongodb import mongo_db
from app.services.feedbackBoard.schemas import FeedbackWeeklyReport

report_col = mongo_db["feedback_weekly_reports"]


def upsert_weekly_report(report: FeedbackWeeklyReport) -> FeedbackWeeklyReport:
    """
    (camp_id, week, analyzer_version) 기준으로 upsert 저장.
    동일 키가 있으면 덮어쓰고, 없으면 생성.
    """
    key = {
        "camp_id": report.camp_id,
        "week": report.week,
        "analyzer_version": report.analyzer_version,
    }

    doc = report.model_dump(by_alias=True)

    report_col.update_one(
        key,
        {"$set": doc},
        upsert=True,
    )

    saved = report_col.find_one(key)
    return FeedbackWeeklyReport(**saved)


def get_weekly_report(camp_id: int, week: int, analyzer_version: str = "fb_v1") -> Optional[FeedbackWeeklyReport]:
    doc = report_col.find_one({"camp_id": camp_id, "week": week, "analyzer_version": analyzer_version})
    return FeedbackWeeklyReport(**doc) if doc else None
