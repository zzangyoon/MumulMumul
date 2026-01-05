# app/services/db_service/attendance_daily.py

from __future__ import annotations

from datetime import datetime, date
from typing import List, Optional, Union

from sqlalchemy.orm import Session

from app.core.schemas import AttendanceDaily
from app.services.attendance.schemas import AttendanceResult


# -----------------------------
# internal utils
# -----------------------------
def _to_date(x: Union[datetime, date]) -> date:
    return x.date() if isinstance(x, datetime) else x


# -----------------------------
# query
# -----------------------------
def get_attendance_daily_before_date(
    db: Session,
    camp_id: int,
    user_id: int,
    target_dt: Union[datetime, date],
) -> List[AttendanceDaily]:
    """
    target_dt(<=)까지의 출결 기록 조회
    - target_dt는 datetime/date 모두 허용
    - 주말(토/일)은 제외
    """
    target_date = _to_date(target_dt)

    logs = (
        db.query(AttendanceDaily)
        .filter(
            AttendanceDaily.camp_id == camp_id,
            AttendanceDaily.user_id == user_id,
            AttendanceDaily.date <= target_date,
        )
        .order_by(AttendanceDaily.date.asc())
        .all()
    )

    # ✅ 주말 제외(안전하게 여기서도 한 번 더)
    logs = [r for r in logs if (r.date.weekday() < 5)]

    # print는 운영 시 과하니 필요하면 로거로 바꾸는 걸 추천
    # print("daily 출결 기록 조회:", [(r.user_id, r.date, r.attendance_type) for r in logs])

    return logs


# -----------------------------
# upsert
# -----------------------------
def save_attendance_daily(
    db: Session,
    camp_id: int,
    target_dt: Union[datetime, date],
    daily_results: List[AttendanceResult],
) -> None:
    """
    AttendanceDaily upsert
    - key: (camp_id, user_id, date)
    - daily_results: AttendanceResult 리스트
      - result.user_id
      - result.attendance_type
      - result.features.total_active_time / first_join / last_leave / never_joined (Optional)
    """
    if not daily_results:
        return

    target_date = _to_date(target_dt)

    # ✅ 주말이면 저장 자체를 스킵(정책: 주말 출결 미집계)
    if target_date.weekday() >= 5:
        return

    for result in daily_results:
        user_id = result.user_id
        attendance_type = result.attendance_type
        features = getattr(result, "features", None)

        existing: Optional[AttendanceDaily] = (
            db.query(AttendanceDaily)
            .filter(
                AttendanceDaily.camp_id == camp_id,
                AttendanceDaily.user_id == user_id,
                AttendanceDaily.date == target_date,
            )
            .one_or_none()
        )

        if existing:
            # 업데이트
            existing.attendance_type = attendance_type
            if features is not None:
                existing.total_active_time = getattr(features, "total_active_time", None)
                existing.first_join = getattr(features, "first_join", None)
                existing.last_leave = getattr(features, "last_leave", None)
                existing.never_joined = getattr(features, "never_joined", None)
        else:
            # 신규 생성
            new_row = AttendanceDaily(
                camp_id=camp_id,
                user_id=user_id,
                date=target_date,
                attendance_type=attendance_type,
                total_active_time=getattr(features, "total_active_time", None) if features is not None else None,
                first_join=getattr(features, "first_join", None) if features is not None else None,
                last_leave=getattr(features, "last_leave", None) if features is not None else None,
                never_joined=getattr(features, "never_joined", None) if features is not None else None,
            )
            db.add(new_row)

    db.commit()
    return
