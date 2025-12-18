# app/services/attendance/calculator.py

from datetime import datetime, date, time, timedelta
from collections import defaultdict
from typing import List, Dict, Tuple

from app.core.schemas import DailyAttendance, SessionActivityLog, Camp, User

MORNING_START = time(9, 0)
MORNING_END   = time(12, 0)
AFTERNOON_START = time(13, 0)
AFTERNOON_END   = time(18, 0)

FULL_DAY_MINUTES = 8 * 60  # 480분


def _overlap_minutes(
    start: datetime,
    end: datetime,
    block_start_t: time,
    block_end_t: time,
) -> int:
    """특정 구간(start~end)과 하루 내 시간 블록의 겹치는 분(minute) 계산."""
    if start >= end:
        return 0

    block_start = datetime.combine(start.date(), block_start_t)
    block_end = datetime.combine(start.date(), block_end_t)

    s = max(start, block_start)
    e = min(end, block_end)

    if s >= e:
        return 0

    return int((e - s).total_seconds() // 60)


def classify_attendance_status(
    total_minutes: int,
    morning_minutes: int,
    afternoon_minutes: int,
) -> str:
    """
    일 단위 출결 상태 판별 로직.

    대략적인 기준 (필요하면 이후 튜닝):
    - 0분: 결석
    - 480분의 80% 이상 + 오전/오후 둘 다 참여: 정상
    - 오전 0, 오후만 참여: 지각
    - 오후 0, 오전만 참여: 조퇴
    - 그 외: 부분참여
    """
    if total_minutes <= 0:
        return "결석"

    if (
        total_minutes >= FULL_DAY_MINUTES * 0.8
        and morning_minutes > 0
        and afternoon_minutes > 0
    ):
        return "정상"

    if morning_minutes == 0 and afternoon_minutes > 0:
        return "지각"

    if morning_minutes > 0 and afternoon_minutes == 0:
        return "조퇴"

    return "부분참여"


def aggregate_daily_attendance(
    camp: Camp,
    students: List[User],
    logs: List[SessionActivityLog],
    start_date: date,
    end_date: date,
) -> List[DailyAttendance]:
    """
    SessionActivityLog → DailyAttendance 일 단위 집계.

    - 주어진 기간(start_date ~ end_date) 동안
    - 모든 수강생(student) × 날짜 조합에 대해 DailyAttendance 1행 생성
      (로그가 없어도 '결석'으로 한 행 생김)
    """

    # (1) 기본 구조: {(user_id, date): {"total": .., "morning": .., "afternoon": ..}}
    minutes_map: Dict[Tuple[int, date], Dict[str, int]] = defaultdict(
        lambda: {"total": 0, "morning": 0, "afternoon": 0}
    )

    # (2) SessionActivityLog → 일자별 분배
    for log in logs:
        user_id = log.user_id
        current_start = log.join_at
        end_dt = log.leave_at

        # 로그가 기간 밖이면 스킵
        if current_start.date() > end_date or end_dt.date() < start_date:
            continue

        # 날짜별로 끊어서 처리 (자정 넘어가는 케이스 포함)
        while current_start < end_dt:
            current_date = current_start.date()
            if current_date > end_date:
                break

            day_end = datetime.combine(current_date, time(23, 59, 59))
            seg_end = min(end_dt, day_end)

            if current_date >= start_date:
                key = (user_id, current_date)

                seg_minutes = int((seg_end - current_start).total_seconds() // 60)

                # 전체 시간
                minutes_map[key]["total"] += seg_minutes

                # 오전/오후 블록별
                minutes_map[key]["morning"] += _overlap_minutes(
                    current_start, seg_end, MORNING_START, MORNING_END
                )
                minutes_map[key]["afternoon"] += _overlap_minutes(
                    current_start, seg_end, AFTERNOON_START, AFTERNOON_END
                )

            # 다음 날로 이동
            current_start = datetime.combine(current_date, time(0, 0)) + timedelta(days=1)

    # (3) 기간 내 모든 날짜/학생 조합에 대해 행 만들어주기 (로그 없어도 결석 처리)
    all_dates: List[date] = []
    d = start_date
    while d <= end_date:
        all_dates.append(d)
        d += timedelta(days=1)

    result: List[DailyAttendance] = []

    student_ids = [s.user_id for s in students]

    for day in all_dates:
        for user_id in student_ids:
            key = (user_id, day)
            agg = minutes_map.get(key, {"total": 0, "morning": 0, "afternoon": 0})

            total = int(agg["total"])
            morning = int(agg["morning"])
            afternoon = int(agg["afternoon"])

            status = classify_attendance_status(total, morning, afternoon)

            result.append(
                DailyAttendance(
                    camp_id=camp.camp_id,
                    user_id=user_id,
                    date=day,
                    total_minutes=total,
                    morning_minutes=morning,
                    afternoon_minutes=afternoon,
                    status=status,
                )
            )

    return result
