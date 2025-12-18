from datetime import datetime, time
from enum import Enum
from typing import Optional, List
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.core.schemas import AttendanceType
from app.services.db_service.session_activity_log import get_session_activity_logs_for_camp_today
from app.services.attendance.schemas import AttendanceRuleset

class AttendanceResult(BaseModel):
    student_id: int
    attendance_type: AttendanceType
    features: AttendanceFeature

FULL_DAY_MINUTES = 8 * 60
START_TIME = time(9, 0)
END_TIME = time(18, 0)
LUNCH_START = time(12, 0)
LUNCH_END = time(13, 0)

def _judge_one_student(
    user_id: int,
    logs: List,
) -> AttendanceResult:
    """
    return:
      attendance_type, evidence_features(dict)
    """
    # 로그를 체크하는 시간이 언제인지에 따라 달라짐
    # 오전 9시 - 12시 사이 체크시 : 지각 판단 가능, 결석 판단 불가능
    # 오후 1시 - 6시 사이 체크시 : 조퇴 판단 가능, 결석 판단 가능
    # 저녁 6시 이후 체크시 : 모두 판단 가능
    # 이 내용은 규칙셋을 반영 할것
    current_time = datetime.now().time()
    can_judge_absent = current_time >= time(13, 0)  # 오후 1시 이후
    can_judge_early_leave = current_time >= time(18, 0)  # 오후 6시 이후
    can_judge_late = current_time >= time(9, 0)  # 오전 9시 이후

    # 2) ABSENT 결석 판단
    if can_judge_absent and not logs:
        return AttendanceResult(
                student_id=user_id,
                attendance_type=AttendanceType.ABSENT, 
                features=AttendanceFeature(never_joined=True))

    # 3) 지각 / 조퇴 / 출석 판단
    # 결설 판단: 활동 시간이 4시간 미만인 경우 결석으로 간주
    active_periods = []
    for log in logs:
        if log.leave_at and log.join_at:
            active_periods.append((log.join_at, log.leave_at))
    total_active_minutes = sum(
        (leave - join).total_seconds() / 60 for join, leave in active_periods
    )
    if total_active_minutes < (FULL_DAY_MINUTES / 2) and can_judge_absent:
        return AttendanceResult(
                student_id=user_id,
                attendance_type=AttendanceType.ABSENT, 
                features=AttendanceFeature(total_active_time=total_active_minutes))

    # 조퇴 판단
    if can_judge_early_leave:
        last_leave = max(log.leave_at for log in logs)
        if last_leave.time() < time(18, 0):
            return AttendanceResult(
                student_id=user_id,
                attendance_type=AttendanceType.EARLY_LEAVE, 
                features=AttendanceFeature(last_leave=last_leave))
        
    # 지각 판단
    if can_judge_late:
        first_join = min(log.join_at for log in logs)
        if first_join.time() > time(9, 0):
            return AttendanceResult(
                student_id=user_id,
                attendance_type=AttendanceType.LATE,
                features=AttendanceFeature(first_join=first_join))
    
    # 기본 출석 판단
    attendance_type = AttendanceType.PRESENT

    return AttendanceResult(
        student_id=user_id,
        attendance_type=attendance_type,
        features=AttendanceFeature(total_active_time=total_active_minutes))


def judge_attendance_for_students(
    db: Session,
    camp_id: int,
    day_start: datetime,
    day_end: datetime,
    ruleset_doc: AttendanceRuleset) -> List[AttendanceResult]:

    # 1) 오늘 로그 조회
    logs = get_session_activity_logs_for_camp_today(
        db, camp_id, day_start, day_end)

    
    # Global값 설정
    FULL_DAY_MINUTES = ruleset_doc.full_day_minutes if ruleset_doc and ruleset_doc.full_day_minutes else 8 * 60
    START_TIME = ruleset_doc.start_time.time() if ruleset_doc and ruleset_doc.start_time else time(9, 0)
    END_TIME = ruleset_doc.end_time.time() if ruleset_doc and ruleset_doc.end_time else time(18, 0)
    LUNCH_START = ruleset_doc.lunch_start.time() if ruleset_doc and ruleset_doc.lunch_start else time(12, 0)
    LUNCH_END = ruleset_doc.lunch_end.time() if ruleset_doc and ruleset_doc.lunch_end else time(13, 0)

    # 2) 학생별 출결 판단
    attendance_results = []
    for user_id in set(log.user_id for log in logs):
        user_logs = [log for log in logs if log.user_id == user_id]
        result = _judge_one_student(user_id, user_logs)
        attendance_results.append(result)
    
    return attendance_results
