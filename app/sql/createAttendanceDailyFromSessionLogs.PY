# app/sql/createAttendanceDailyFromSessionLogs.py

import sys
from pathlib import Path

# 프로젝트 루트 설정
CURRENT_FILE = Path(__file__).resolve()
ROOT_DIR = CURRENT_FILE.parents[2]
sys.path.append(str(ROOT_DIR))

from datetime import datetime, timedelta, time, date
from typing import Dict, List, Tuple, Optional

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.core.db import SessionLocal  # 프로젝트에 맞게
from app.core.schemas import SessionActivityLog  # 프로젝트에 맞게
from app.core.schemas import AttendanceDaily     # 프로젝트에 맞게 (너가 올린 AttendanceDaily 모델)

CAMP_ID = 1
START_DATE = date(2025, 12, 1)
END_DATE = (datetime(2025, 12, 1) + timedelta(weeks=6)).date()

# 출결 판정 기준(원하는대로 조정)
WORK_START = time(9, 0)
WORK_END = time(18, 0)

# "몇 분 이상 늦으면 지각인가?"
LATE_CUTOFF = time(9, 10)          # 09:10 이후 first_join이면 LATE 처리
# "몇 시 이전 퇴장하면 조퇴인가?"
EARLY_LEAVE_CUTOFF = time(17, 50)  # 17:50 이전 last_leave이면 EARLY_LEAVE 처리


def iter_weekdays(start: date, end: date):
    cur = start
    while cur <= end:
        if cur.weekday() < 5:  # Mon~Fri
            yield cur
        cur += timedelta(days=1)


def safe_minutes(delta: timedelta) -> int:
    mins = int(delta.total_seconds() // 60)
    return max(0, mins)


def classify_attendance(first_join_dt: Optional[datetime], last_leave_dt: Optional[datetime], has_logs: bool) -> Tuple[str, bool]:
    """
    attendance_type, never_joined
    """
    if not has_logs or not first_join_dt or not last_leave_dt:
        return "ABSENT", True

    never_joined = False
    first_t = first_join_dt.time()
    last_t = last_leave_dt.time()

    # 정책: 지각 우선, 그 다음 조퇴, 그 다음 정상
    if first_t > LATE_CUTOFF:
        return "LATE", never_joined
    if last_t < EARLY_LEAVE_CUTOFF:
        return "EARLY_LEAVE", never_joined
    return "ON_TIME", never_joined


def upsert_attendance_daily(
    db: Session,
    camp_id: int,
    user_id: int,
    d: date,
    is_finalized: bool,
    attendance_type: str,
    total_active_time: Optional[int],
    first_join: Optional[datetime],
    last_leave: Optional[datetime],
    never_joined: bool,
):
    row = (
        db.query(AttendanceDaily)
        .filter(
            AttendanceDaily.camp_id == camp_id,
            AttendanceDaily.user_id == user_id,
            AttendanceDaily.date == d,
        )
        .one_or_none()
    )

    if row is None:
        row = AttendanceDaily(
            camp_id=camp_id,
            user_id=user_id,
            date=d,
            is_finalized=is_finalized,
            attendance_type=attendance_type,
            total_active_time=total_active_time,
            first_join=first_join,
            last_leave=last_leave,
            never_joined=never_joined,
        )
        db.add(row)
    else:
        row.is_finalized = is_finalized
        row.attendance_type = attendance_type
        row.total_active_time = total_active_time
        row.first_join = first_join
        row.last_leave = last_leave
        row.never_joined = never_joined
        # updated_at은 onupdate로 자동 갱신


def seed_attendance_daily_from_session_logs():
    db = SessionLocal()
    try:
        # 1) 해당 캠프/기간의 세션 로그 조회
        logs: List[SessionActivityLog] = (
            db.query(SessionActivityLog)
            .filter(
                SessionActivityLog.camp_id == CAMP_ID,
                SessionActivityLog.date >= START_DATE,
                SessionActivityLog.date <= END_DATE,
            )
            .all()
        )

        # 2) (user_id, date)로 그룹핑
        grouped: Dict[Tuple[int, date], List[SessionActivityLog]] = {}
        for log in logs:
            key = (log.user_id, log.date)
            grouped.setdefault(key, []).append(log)

        # 3) 캠프에 포함된 유저 목록 추출 (로그 기반)
        user_ids = sorted({uid for (uid, _) in grouped.keys()})

        # 만약 "캠프 유저 전체(로그 없는 날도 ABSENT로 만들기)"를 원하면,
        # 여기 user_ids를 CampUser 테이블 등에서 가져오면 됨.
        # 지금은 더미가 logs에 항상 어느정도 존재한다는 가정.

        # 4) 모든 평일에 대해 AttendanceDaily 생성/업데이트
        weekdays = list(iter_weekdays(START_DATE, END_DATE))

        upsert_count = 0
        for uid in user_ids:
            for d in weekdays:
                day_logs = grouped.get((uid, d), [])
                has_logs = len(day_logs) > 0

                if not has_logs:
                    attendance_type, never_joined = classify_attendance(None, None, False)
                    upsert_attendance_daily(
                        db=db,
                        camp_id=CAMP_ID,
                        user_id=uid,
                        d=d,
                        is_finalized=True,
                        attendance_type=attendance_type,
                        total_active_time=None,
                        first_join=None,
                        last_leave=None,
                        never_joined=never_joined,
                    )
                    upsert_count += 1
                    continue

                # first_join / last_leave
                first_join = min([x.join_at for x in day_logs if x.join_at is not None], default=None)
                last_leave = max([x.leave_at for x in day_logs if x.leave_at is not None], default=None)

                # total_active_time (분)
                total_minutes = 0
                for x in day_logs:
                    if x.join_at is None or x.leave_at is None:
                        continue
                    total_minutes += safe_minutes(x.leave_at - x.join_at)

                attendance_type, never_joined = classify_attendance(first_join, last_leave, True)

                upsert_attendance_daily(
                    db=db,
                    camp_id=CAMP_ID,
                    user_id=uid,
                    d=d,
                    is_finalized=True,
                    attendance_type=attendance_type,
                    total_active_time=total_minutes,
                    first_join=first_join,
                    last_leave=last_leave,
                    never_joined=never_joined,
                )
                upsert_count += 1

        db.commit()
        print(f"✅ attendance_daily upserted: {upsert_count} rows")

    finally:
        db.close()


if __name__ == "__main__":
    seed_attendance_daily_from_session_logs()
