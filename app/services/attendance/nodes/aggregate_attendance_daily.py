from datetime import datetime, timedelta, date
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
    """
    AttendanceDaily 기반 AttendanceReport 집계

    ✅ 수정 포인트
    - target_dt(datetime) -> target_date(date)로 변환해서 조회/비교 안정화
    - 주말(토/일) 완전 제외
    - attendance_type 정규화(PRESENT/ON_TIME 등 혼재 방어)
    - never_joined=True면 무조건 ABSENT 처리
    - 연속 결석/지각은 "최근 연속(마지막부터)"로 계산
    - (지각+조퇴 -> 결석 환산) 시 출석률 분자(attended_days)도 함께 보정
    """

    global CONVERT_TO_ABSENT_LATE_PLUS_EARLYLEAVE_UNIT_DEFAULT
    unit = getattr(ruleset_doc, "convert_to_absent_late_plus_earlyleave_unit", None) if ruleset_doc else None
    if unit is not None:
        try:
            CONVERT_TO_ABSENT_LATE_PLUS_EARLYLEAVE_UNIT_DEFAULT = int(unit)
        except Exception:
            pass

    # -------------------------
    # 내부 유틸
    # -------------------------
    def _raw_str(x: Any) -> str:
        if x is None:
            return ""
        return x.value if hasattr(x, "value") else str(x)

    def _normalize_type(record: AttendanceDaily) -> str:
        """
        AttendanceDaily row를 안전하게 AttendanceType 문자열로 정규화
        """
        if getattr(record, "never_joined", False) is True:
            return AttendanceType.ABSENT.value

        s = _raw_str(getattr(record, "attendance_type", None)).strip().upper()

        # 과거 데이터/혼재 방어
        if s in ("", "NONE"):
            return AttendanceType.UNKNOWN.value
        if s in ("PRESENT",):  # 과거 값 호환
            return AttendanceType.ON_TIME.value

        # 정상 케이스
        if s in (
            AttendanceType.ON_TIME.value,
            AttendanceType.LATE.value,
            AttendanceType.EARLY_LEAVE.value,
            AttendanceType.ABSENT.value,
            AttendanceType.UNKNOWN.value,
        ):
            return s

        # 잘린 값 등 방어
        if s.startswith("EARLY"):
            return AttendanceType.EARLY_LEAVE.value

        return AttendanceType.UNKNOWN.value

    def _abbr(att_type: str) -> str:
        if not att_type:
            return "-"
        return att_type[:1]  # O/L/E/A/U

    def _is_weekday(d: Any) -> bool:
        """
        d가 date 또는 datetime일 때 모두 대응
        """
        if isinstance(d, datetime):
            d = d.date()
        if not isinstance(d, date):
            return False
        return d.weekday() < 5

    def _is_attended(att_type: str) -> bool:
        return att_type in (
            AttendanceType.ON_TIME.value,
            AttendanceType.LATE.value,
            AttendanceType.EARLY_LEAVE.value,
        )

    # -------------------------
    # 참여일(평일) 계산
    # -------------------------
    total_participation_days = 0
    curr_date = start_date
    while curr_date <= end_date:
        if curr_date.weekday() < 5:
            total_participation_days += 1
        curr_date += timedelta(days=1)

    students_stats: List[AttendanceStudentStat] = []

    # ✅ summary 누적
    sum_on_time = 0
    sum_late = 0
    sum_early = 0
    sum_absent = 0
    sum_unknown = 0

    sum_finalized_days = 0   # (ON_TIME/LATE/EARLY/ABSENT) 합 (환산 반영 후)
    sum_attended_days = 0    # 출석으로 치는 날 수 (환산 반영 후)

    # ✅ target_dt -> date 로 고정 (Date 컬럼 비교 안정화)
    target_date = target_dt.date()

    for student in students:
        attendance_records = get_attendance_daily_before_date(db, camp_id, student.user_id, target_date) or []
        if not isinstance(attendance_records, list):
            attendance_records = [attendance_records]

        # ✅ 주말 제외
        attendance_records = [r for r in attendance_records if _is_weekday(getattr(r, "date", None))]
        attendance_records.sort(key=lambda x: x.date)

        absent_count = 0
        late_count = 0
        early_leave_count = 0
        on_time_count = 0
        unknown_count = 0

        # 출석률 분자(출석으로 치는 날)
        attended_days = 0

        # 최근 30일 요약에 쓸 정규화 타입 캐시
        normalized_types: List[str] = []

        for record in attendance_records:
            rtype = _normalize_type(record)
            normalized_types.append(rtype)

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
            else:
                unknown_count += 1

        # ✅ 환산 규칙(지각+조퇴 -> 결석) + 출석률 분자도 보정
        converted_to_absent = 0
        unit_val = max(1, int(CONVERT_TO_ABSENT_LATE_PLUS_EARLYLEAVE_UNIT_DEFAULT or 1))
        if (late_count + early_leave_count) >= unit_val:
            converted_to_absent = (late_count + early_leave_count) // unit_val
            absent_count += converted_to_absent
            attended_days = max(0, attended_days - converted_to_absent)

        # ✅ 출석률: UNKNOWN 제외한 "확정일수"로 나눔(환산 반영 후)
        finalized_days = on_time_count + late_count + early_leave_count + absent_count
        attendance_rate = (attended_days / finalized_days) if finalized_days > 0 else 0.0

        # 최근 30일 요약
        last_30 = normalized_types[-30:] if normalized_types else []
        recent_30_attendance_summary = " ".join(
            f"{i+1}일:{_abbr(t)}" for i, t in enumerate(last_30)
        ) if last_30 else ""

        # ✅ 연속 결석(최근 연속: 끝에서부터)
        consecutive_absent_days = 0
        for t in reversed(normalized_types):
            if t == AttendanceType.ABSENT.value:
                consecutive_absent_days += 1
            else:
                break

        # ✅ 연속 지각(최근 연속)
        consecutive_late_days = 0
        for t in reversed(normalized_types):
            if t == AttendanceType.LATE.value:
                consecutive_late_days += 1
            else:
                break

        # 최근 7/14/30 출석률(평일 기준 최근 N개 record)
        def _rate_last_n(n: int) -> float:
            if not normalized_types:
                return 0.0
            window = normalized_types[-n:] if len(normalized_types) >= n else normalized_types
            den = len(window) or 1
            num = sum(1 for t in window if _is_attended(t))
            return num / den

        attendance_rate_7d = _rate_last_n(7)
        attendance_rate_14d = _rate_last_n(14)
        attendance_rate_30d = _rate_last_n(30)

        student_stat = AttendanceStudentStat(
            user_id=student.user_id,
            name=getattr(student, "name", None) or getattr(student, "real_name", None) or str(student.user_id),

            attendance_rate=attendance_rate,
            absent_count=absent_count,
            late_count=late_count,
            early_leave_count=early_leave_count,

            # ✅ 추가 필드
            on_time_count=on_time_count,
            unknown_count=unknown_count,

            personality_type=getattr(student, "tendency_type_code", None) or "검사 결과 없음",

            attendance_records=[
                {
                    "date": (record.date.isoformat() if hasattr(record.date, "isoformat") else str(record.date)),
                    "attendance_type": _normalize_type(record),  # ✅ 정규화 결과로 저장
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

        # ✅ summary 누적(환산 반영된 absent / attended / finalized 기준)
        sum_on_time += on_time_count
        sum_late += late_count
        sum_early += early_leave_count
        sum_absent += absent_count
        sum_unknown += unknown_count

        sum_finalized_days += finalized_days
        sum_attended_days += attended_days

    total_students = len(students_stats)

    # ✅ summary: UNKNOWN 제외 분모(확정일수) 기반
    attendance_rate_summary = (sum_attended_days / sum_finalized_days) if sum_finalized_days > 0 else 0.0
    late_rate_summary = (sum_late / sum_finalized_days) if sum_finalized_days > 0 else 0.0

    summary = AttendanceSummary(
        attendance_rate=attendance_rate_summary,
        total_students=total_students,
        late_rate=late_rate_summary,

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
