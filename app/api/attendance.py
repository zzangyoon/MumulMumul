# app/api/attendance.py
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.mongodb import get_mongo_db
from app.services.attendance.schemas import AttendanceReport
from app.services.attendance.service import generate_attendance_report
from app.services.db_service.attendance_report import get_attendance_report
from app.core.timezone import isoformat_to_datetime
router = APIRouter()

@router.get("/report", response_model=AttendanceReport)
def fetch_attendance_report(
    camp_id: int = Query(..., description="리포트를 조회할 캠프 ID"),
    target_date: str = Query(..., alias="target_date", description="리포트를 조회할 날짜"),
):
    """
    출결 리포트 조회 API
    """
    payload = get_attendance_report(
        camp_id=camp_id,
        target_date=isoformat_to_datetime(target_date),
    )
    if payload is None:
        raise HTTPException(status_code=404, detail="Attendance report not found")
    return payload

class AttendanceReportRequest(BaseModel):
    camp_id: int
    target_date: datetime

@router.post("/report/generate", response_model=AttendanceReport)
def create_attendance_report(
    payload: AttendanceReportRequest,
    db: Session = Depends(get_db),
    mongo = Depends(get_mongo_db)
):
    """
    출결 리포트 생성 API
    """
    report = generate_attendance_report(
        camp_id=payload.camp_id,
        target_date=payload.target_date,
        db=db,
        mongo=mongo,  # MongoDB 사용 시 여기에 MongoDB 세션을 전달하세요
    )
    return report
