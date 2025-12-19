from datetime import datetime, timedelta
from typing import Any, List, Optional

from sqlalchemy.orm import Session

from app.core.schemas import User, AttendanceType, AttendanceDaily

from app.services.attendance.schemas import (
    AttendanceReport,
    AttendanceStudentStat,
    AttendanceSummary,
    CompileRuleset,
)
from app.services.db_service.attendance_daily import get_attendance_daily_before_date

CONVERT_TO_ABSENT_LATE_PLUS_EARLYLEAVE_UNIT_DEFAULT = 3


def aggregate_attendance_daily(
    db: Session,
    camp_id: int,
    camp_name: str,
    start_date: datetime,
    end_date: datetime,
    target_dt: datetime,
    students: List[User],
    ruleset_doc: CompileRuleset | None,
) -> AttendanceReport:

    global CONVERT_TO_ABSENT_LATE_PLUS_EARLYLEAVE_UNIT_DEFAULT
    unit = getattr(ruleset_doc, "convert_to_absent_late_plus_earlyleave_unit", None) if ruleset_doc else None
    if unit is not None:
        try:
            CONVERT_TO_ABSENT_LATE_PLUS_EARLYLEAVE_UNIT_DEFAULT = int(unit)
        except Exception:
            pass

    def _atype(x: Any) -> str:
        if x is None:
            return ""
        return x.value if hasattr(x, "value") else str(x)

    def _abbr(x: Any) -> str:
        s = _atype(x)
        return s[:1] if s else "-"

    # 참여일(평일) 계산
    total_participation_days = 0
    curr_date = start_date
    while curr_date <= end_date:
        if curr_date.weekday() < 5:
            total_participation_days += 1
        curr_date += timedelta(days=1)

    students_stats: List[AttendanceStudentStat] = []

    # ✅ summary용 전체 합계 카운트
    sum_on_time = 0
    sum_late = 0
    sum_early = 0
    sum_absent = 0
    sum_unknown = 0

    for student in students:
        attendance_records = get_attendance_daily_before_date(db, camp_id, student.user_id, target_dt) or []
        if not isinstance(attendance_records, list):
            attendance_records = [attendance_records]

        attendance_records.sort(key=lambda x: x.date)

        # ✅ 학생별 카운트
        absent_count = 0
        late_count = 0
        early_leave_count = 0
        on_time_count = 0
        unknown_count = 0

        # 출석률 분자(출석으로 치는 날: 정상/지각/조퇴)
        attended_days = 0

        for record in attendance_records:
            rtype = _atype(record.attendance_type)

            if rtype == AttendanceType.ABSENT.value:
                absent_count += 1
            elif rtype == AttendanceType.LATE.value:
                late_count += 1
                attended_days += 1
            elif rtype == AttendanceType.EARLY_LEAVE.value:
                early_leave_count += 1
                attended_days += 1
            elif rtype == AttendanceType.ON_TIME.value:
                on_time_count += 1
                attended_days += 1
            elif rtype == AttendanceType.UNKNOWN.value:
                unknown_count += 1

        # ✅ 환산 규칙(지각+조퇴 -> 결석)
        if late_count + early_leave_count >= CONVERT_TO_ABSENT_LATE_PLUS_EARLYLEAVE_UNIT_DEFAULT:
            absent_count += (late_count + early_leave_count) // CONVERT_TO_ABSENT_LATE_PLUS_EARLYLEAVE_UNIT_DEFAULT

        # ✅ 출석률: UNKNOWN은 분모에서 제외하려면 “확정일수”로 나눔
        # 확정일수 = (정상/지각/조퇴/결석) 총합
        finalized_days = on_time_count + late_count + early_leave_count + absent_count
        attendance_rate = (attended_days / finalized_days) if finalized_days > 0 else 0.0

        recent_30_attendance_summary = " ".join(
            f"{i+1}일:{_abbr(r.attendance_type)}" for i, r in enumerate(attendance_records[-30:])
        )

        # 연속 결석
        consecutive_absent_days = 0
        cur_consec = 0
        for record in reversed(attendance_records):
            if _atype(record.attendance_type) == AttendanceType.ABSENT.value:
                cur_consec += 1
                consecutive_absent_days = max(consecutive_absent_days, cur_consec)
            else:
                cur_consec = 0

        # 연속 지각
        consecutive_late_days = 0
        cur_consec = 0
        for record in reversed(attendance_records):
            if _atype(record.attendance_type) == AttendanceType.LATE.value:
                cur_consec += 1
                consecutive_late_days = max(consecutive_late_days, cur_consec)
            else:
                cur_consec = 0

        den7 = min(7, len(attendance_records)) or 1
        den14 = min(14, len(attendance_records)) or 1
        den30 = min(30, len(attendance_records)) or 1

        attendance_rate_7d = (
            sum(1 for record in attendance_records[-7:] if _atype(record.attendance_type) == AttendanceType.ON_TIME.value)
            / den7
        )
        attendance_rate_14d = (
            sum(1 for record in attendance_records[-14:] if _atype(record.attendance_type) == AttendanceType.ON_TIME.value)
            / den14
        )
        attendance_rate_30d = (
            sum(1 for record in attendance_records[-30:] if _atype(record.attendance_type) == AttendanceType.ON_TIME.value)
            / den30
        )

        student_stat = AttendanceStudentStat(
            user_id=student.user_id,
            name=getattr(student, "name", None) or getattr(student, "real_name", None) or str(student.user_id),

            attendance_rate=attendance_rate,
            absent_count=absent_count,
            late_count=late_count,
            early_leave_count=early_leave_count,

            # ✅ 추가
            on_time_count=on_time_count,
            unknown_count=unknown_count,

            personality_type=getattr(student, "tendency_type_code", None) or "검사 결과 없음",
            attendance_records=[
                {
                    "date": record.date.isoformat() if hasattr(record.date, "isoformat") else str(record.date),
                    "attendance_type": _atype(record.attendance_type),
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

        # ✅ summary 누적
        sum_on_time += on_time_count
        sum_late += late_count
        sum_early += early_leave_count
        sum_absent += absent_count
        sum_unknown += unknown_count

    # ✅ summary 계산 (UNKNOWN 제외한 분모 기반)
    total_students = len(students_stats)

    finalized_total = sum_on_time + sum_late + sum_early + sum_absent
    attended_total = sum_on_time + sum_late + sum_early

    attendance_rate_summary = (attended_total / finalized_total) if finalized_total > 0 else 0.0
    late_rate_summary = (sum_late / finalized_total) if finalized_total > 0 else 0.0

    summary = AttendanceSummary(
        attendance_rate=attendance_rate_summary,
        total_students=total_students,
        late_rate=late_rate_summary,

        # ✅ 빠진 카운트들 추가
        on_time_count=sum_on_time,
        late_count=sum_late,
        early_leave_count=sum_early,
        absent_count=sum_absent,
        unknown_count=sum_unknown,
    )

    return AttendanceReport(
        camp_id=camp_id,
        camp_name=camp_name,
        target_date=target_dt,
        summary=summary,
        students_stat=students_stats,
    )
