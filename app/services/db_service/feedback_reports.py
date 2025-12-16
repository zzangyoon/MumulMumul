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
    """
    key = {
        "camp_id": report.camp_id,
        "week": report.week,
        "analyzer_version": report.analyzer_version,
    }

    doc = report.model_dump(by_alias=True)

    # 동일 key가 있으면 업데이트
    if report_col.count_documents(key) > 0:
        report_col.replace_one(
            key,
            doc,
            upsert=True,
        )
    else:
        report_col.insert_one(doc)

    saved = report_col.find_one(key)
    return FeedbackWeeklyReport(**saved)


def get_weekly_report(camp_id: int, week: int, analyzer_version: str = "fb_v1") -> Optional[FeedbackWeeklyReport]:
    doc = report_col.find_one({"camp_id": camp_id, "week": week, "analyzer_version": analyzer_version})
    return FeedbackWeeklyReport(**doc) if doc else None
