from datetime import datetime, time, timedelta
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.schemas import AttendanceDaily, AttendanceType, SessionActivityLog, User
from app.services.attendance.schemas import AttendanceResult, CompileRuleset

ABSENT_IF_TOTAL_MINUTES_LTE = 240  # 4시간


def judge_attendance_for_students(
    db: Session,
    camp_id: int,
    day_start: datetime,
    day_end: datetime,
    students: List[User],
    ruleset_doc: Optional[CompileRuleset],
) -> List[AttendanceResult]:
    # rule은 start/end만
    start_time: time = ruleset_doc.start_time.time() if ruleset_doc and getattr(ruleset_doc, "start_time", None) else time(9, 0)
    end_time: time = ruleset_doc.end_time.time() if ruleset_doc and getattr(ruleset_doc, "end_time", None) else time(18, 0)

    start_day = day_start.replace(hour=0, minute=0, second=0, microsecond=0)
    end_day = day_end.replace(hour=0, minute=0, second=0, microsecond=0)
    if end_day < start_day:
        end_day = start_day

    now = datetime.now()
    results: List[AttendanceResult] = []

    cur = start_day
    while cur <= end_day:
        d_start = cur
        d_end = d_start + timedelta(days=1)

        # day logs
        day_logs: List[SessionActivityLog] = (
            db.query(SessionActivityLog)
            .filter(
                SessionActivityLog.camp_id == camp_id,
                SessionActivityLog.join_at >= d_start,
                SessionActivityLog.join_at < d_end,
            )
            .all()
        )

        logs_by_user: Dict[int, List[SessionActivityLog]] = {}
        for lg in day_logs:
            logs_by_user.setdefault(lg.user_id, []).append(lg)

        is_past_day = d_start.date() < now.date()
        is_today = d_start.date() == now.date()
        is_work_finished_today = is_today and (now.time() >= end_time)

        is_finalized_day = is_past_day or is_work_finished_today
        is_in_progress_today = is_today and (not is_work_finished_today)

        for student in students:
            user_id = student.user_id

            existing: Optional[AttendanceDaily] = (
                db.query(AttendanceDaily)
                .filter(
                    AttendanceDaily.camp_id == camp_id,
                    AttendanceDaily.user_id == user_id,
                    AttendanceDaily.date == d_start.date(),
                )
                .first()
            )

            # 이미 확정이면 스킵
            if existing and getattr(existing, "is_finalized", False) is True:
                continue

            user_logs = logs_by_user.get(user_id, [])

            # --- 판정 ---
            if not user_logs:
                # 오늘 진행중이면 UNKNOWN, 확정 가능한 날이면 ABSENT
                attendance_type = AttendanceType.UNKNOWN if is_in_progress_today else AttendanceType.ABSENT

            else:
                first_join = min(lg.join_at for lg in user_logs if lg.join_at)
                last_leave = max((lg.leave_at or lg.join_at) for lg in user_logs if lg.join_at)

                total_minutes = 0
                for lg in user_logs:
                    if not lg.join_at:
                        continue
                    leave = lg.leave_at or lg.join_at
                    if leave > lg.join_at:
                        total_minutes += int((leave - lg.join_at).total_seconds() // 60)

                # 활동시간 4시간 이하
                if total_minutes <= ABSENT_IF_TOTAL_MINUTES_LTE:
                    attendance_type = AttendanceType.UNKNOWN if is_in_progress_today else AttendanceType.ABSENT

                # 지각(첫 접속이 9시 이후) — 오늘 진행중이어도 판정 가능
                elif first_join.time() > start_time:
                    attendance_type = AttendanceType.LATE

                # 조퇴(마지막 종료가 6시 이전) — 하루 끝나야 확정 가능
                elif last_leave.time() < end_time:
                    attendance_type = AttendanceType.UNKNOWN if is_in_progress_today else AttendanceType.EARLY_LEAVE

                else:
                    attendance_type = AttendanceType.ON_TIME

            results.append(
                AttendanceResult(
                    user_id=user_id,
                    attendance_type=attendance_type,
                    is_finalized=is_finalized_day,
                    features=None,
                )
            )

            # upsert
            if not existing:
                existing = AttendanceDaily(
                    camp_id=camp_id,
                    user_id=user_id,
                    date=d_start.date(),
                )
                db.add(existing)

            existing.attendance_type = attendance_type.value if hasattr(attendance_type, "value") else str(attendance_type)
            existing.is_finalized = is_finalized_day

        cur += timedelta(days=1)

    db.commit()
    return results
