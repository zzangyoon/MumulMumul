from datetime import datetime, timedelta
from typing import Any, List, Optional
from sqlalchemy.orm import Session
from app.core.schemas import AttendanceType, Camp, AttendanceDaily, User
from app.services.attendance.schemas import AttendanceReport, AttendanceRuleset, AttendanceStudentStat, AttendanceSummary
from app.services.db_service.attendance_daily import get_attendance_records

def aggregate_attendance_daily(
    db: Session,
    camp: Camp,
    target_dt: datetime,
    students: List[User],
    ruleset_doc: AttendanceRuleset,
) -> AttendanceReport:
    """
    로직으로 계산 가능한 부분만 채워서
    AttendanceReport를 반환
    - students: AttendanceStudentStat의 기본 통계만 채움
    - summary: 출석률/총학생수/지각률 카운트만 채움
    """
    # 1) 캠프 참여일 계산
    start = camp.start_date
    end = target_dt.date()

    # 2) 참여일(business days) 계산
    total_participation_days = 0
    curr_date = start
    while curr_date <= end:
        if curr_date.weekday() < 5:  # Mon-Fri
            total_participation_days += 1
        curr_date += timedelta(days=1)

    # 3) 각 학생별 누적 집계
    students_stats = []
    for student in students:
        attendance_records: List[AttendanceDaily] = get_attendance_records(db, camp.camp_id, students[0].user_id, target_dt)
        absent_count = 0
        late_count = 0
        early_leave_count = 0
        on_time_days = 0
        for record in attendance_records:
            if record.attendance_type == AttendanceType.ABSENT.value:
                absent_count += 1
            elif record.attendance_type == AttendanceType.LATE.value:
                late_count += 1
                on_time_days += 1
            elif record.attendance_type == AttendanceType.EARLY_LEAVE.value:
                early_leave_count += 1
                on_time_days += 1
            elif record.attendance_type == AttendanceType.ON_TIME.value:
                on_time_days += 1
            
        if late_count + early_leave_count >= ruleset_doc.convert_to_absent_late_plus_earlyleave_unit:
            absent_count += (late_count + early_leave_count) // ruleset_doc.convert_to_absent_late_plus_earlyleave_unit
       
        attendance_rate = (on_time_days / total_participation_days) if total_participation_days > 0 else 0.0

        recent_30_attendance_summary = " ".join(
            record["attendance_type"][0] for record in student.attendance_records[-30:])
        consecutive_absent_days = 0
        max_consec = 0
        for record in reversed(student.attendance_records):
            if record["attendance_type"] == "ABSENT":
                consecutive_absent_days += 1
                max_consec = max(max_consec, consecutive_absent_days)
            else:
                consecutive_absent_days = 0
        consecutive_absent_days = max_consec
        consecutive_late_days = 0
        max_consec = 0
        for record in reversed(student.attendance_records):
            if record["attendance_type"] == "LATE":
                consecutive_late_days += 1
                max_consec = max(max_consec, consecutive_late_days)
            else:
                consecutive_late_days = 0
        attendance_rate_7d = sum(
            1 for record in student.attendance_records[-7:] 
            if record["attendance_type"] == AttendanceType.ON_TIME.value
        ) / min(7, len(student.attendance_records))
        attendance_rate_14d = sum(
            1 for record in student.attendance_records[-14:] 
            if record["attendance_type"] == AttendanceType.ON_TIME.value
        ) / min(14, len(student.attendance_records))
        attendance_rate_30d = sum(
            1 for record in student.attendance_records[-30:] 
            if record["attendance_type"] == AttendanceType.ON_TIME.value
        ) / min(30, len(student.attendance_records))

        student_stat = AttendanceStudentStat(
            student_id=student.id,
            name=student.name,
            attendance_rate=attendance_rate,
            absent_count=absent_count,
            late_count=late_count,
            early_leave_count=early_leave_count,
            personality_type=student.tendency_type_code,
            attendance_records=[
                {
                    "date": record.date.isoformat(),
                    "attendance_type": record.attendance_type,
                }
                for record in attendance_records
            ],
            recent_30_attendance_summary=recent_30_attendance_summary,
            consecutive_absent_days=consecutive_absent_days,
            consecutive_late_days=consecutive_late_days,
            attendance_rate_7d=attendance_rate_7d,
            attendance_rate_14d=attendance_rate_14d,
            attendance_rate_30d=attendance_rate_30d,
        )

        students_stats.append(student_stat)

    # 4) summary 계산
    total_students = len(students_stats)
    late_students = sum(1 for stat in students_stats if stat.late_count > 0)
    attendance_rate = sum(stat.attendance_rate for stat in students_stats) / total_students if total_students > 0 else 0.0
    late_rate = (late_students / total_students) if total_students > 0 else 0.0
    summary = AttendanceSummary(
        attendance_rate=attendance_rate,
        total_students=total_students,
        late_rate=late_rate,
    )

    # 5) AttendanceReport 객체 생성
    return AttendanceReport(
        camp_id=camp.camp_id,
        camp_name=camp.name,
        target_date=target_dt,
        summary=summary,
        students=students_stats,
    )

