# app/services/db_service/attendance_report.py
from datetime import date, datetime
from typing import Optional
from pymongo.database import Database

from app.core.mongodb import get_mongo_db
from app.services.attendance.schemas import AttendanceReport

mongo_db: Database = get_mongo_db()
report_col = mongo_db["attendance_reports"]


def get_attendance_report(
    camp_id: int,
    target_date: datetime,
) -> Optional[AttendanceReport]:
    doc =report_col.find_one(
        {
            "camp_id": camp_id,
            "target_date": target_date,
        }
    )
    if not doc:
        return None
    return AttendanceReport(**doc)


from datetime import datetime

def upsert_attendance_report(report: AttendanceReport) -> None:
    doc = report.model_dump()
    
    report_col.update_one(
        {"camp_id": doc["camp_id"], "target_date": doc["target_date"]},
        {"$set": doc},
        upsert=True,
    )
