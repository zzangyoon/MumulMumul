from datetime import datetime
from typing import Any, List, Optional
from requests import Session

from app.core.schemas import AttendanceDaily
from app.services.attendance.schemas import AttendanceResult

def get_attendance_records(db:Session, camp_id: int, student_id: int, target_dt: datetime) -> List[AttendanceDaily]:
    return db.query(AttendanceDaily).filter(
        AttendanceDaily.camp_id == camp_id,
        AttendanceDaily.student_id == student_id,
        AttendanceDaily.date <= target_dt.date()
    ).all()

def save_attendance_daily(
    db: Session,
    camp_id: int,
    target_dt: datetime,
    daily_results: List[AttendanceResult],
):
    """
    results item 예:
      {
        "student_id": 123,
        "attendance_type": "...",
        "active_minutes": ...,
        "max_inactive_gap_minutes": ...,
      }
    """
    # day = target_dt.date()
    # AttendanceDaily upsert
    #     - (camp_id, student_id, date) unique
    #     - attendance_type 저장
    #     - active_minutes/max_gap 저장 (없으면 null)
    # AttendanceDaily 항목이 없으면 생성, 있으면 업데이트
    if not daily_results:
        return
    
    for result in daily_results:
        student_id = result.student_id
        attendance_type = result.attendance_type
        features = result.features

        existing_record: Optional[Any] = db.query(
            AttendanceDaily
        ).filter_by(
            camp_id=camp_id,
            student_id=student_id,
            date=target_dt.date()
        ).first()

        if existing_record:
            # 업데이트
            existing_record.attendance_type = attendance_type
            existing_record.total_active_time = features.total_active_time
            existing_record.first_join = features.first_join
            existing_record.last_leave = features.last_leave
            existing_record.never_joined = features.never_joined
        else:
            # 신규 생성
            new_record = AttendanceDaily(
                camp_id=camp_id,
                student_id=student_id,
                date=target_dt.date(),
                attendance_type=attendance_type,
                total_active_time=features.total_active_time,
                first_join=features.first_join,
                last_leave=features.last_leave,
                never_joined=features.never_joined,
            )
            db.add(new_record)

    db.commit()
    return
