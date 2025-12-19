from datetime import datetime
from typing import List
from requests import Session

from app.core.schemas import SessionActivityLog, User

# 특정 캠프 오늘 날짜의 출석 활동 로그를 모두 가져옵니다.
def get_session_activity_logs_for_camp_today(
    db: Session,
    camp_id: int,
    day_start: datetime,
    day_end: datetime,
) -> List[SessionActivityLog]:
    """
    특정 캠프의 오늘 날짜에 해당하는 SessionActivityLog 레코드를 모두 조회합니다
    """
    logs: List[SessionActivityLog] = (
        db.query(SessionActivityLog)
        .join(User, SessionActivityLog.user_id == User.user_id)
        .filter(
            User.camp_id == camp_id,
            SessionActivityLog.join_at >= day_start,
            SessionActivityLog.join_at < day_end,
        )
        .all()
    )
    return logs

def get_all_session_activity_logs_for_camp(
    db: Session,
    camp_id: int,
) -> List[SessionActivityLog]:
    """
    특정 캠프의 모든 SessionActivityLog 레코드를 조회합니다
    """
    logs: List[SessionActivityLog] = (
        db.query(SessionActivityLog)
        .join(User, SessionActivityLog.user_id == User.user_id)
        .filter(
            User.camp_id == camp_id,
        )
        .all()
    )
    return logs

# 특정 날짜 이전의 특정 유저 세션 활동 로그를 모두 가져옵니다.
def get_session_activity_logs_for_user_before_date(
    db: Session,
    user_id: int,
    target_dt: datetime,
) -> List[SessionActivityLog]:
    """
    특정 유저의 target_dt 이전 날짜의 SessionActivityLog 레코드를 모두 조회합니다
    """
    logs: List[SessionActivityLog] = (
        db.query(SessionActivityLog)
        .join(User, SessionActivityLog.user_id == User.user_id)
        .filter(
            User.user_id == user_id,
            SessionActivityLog.join_at < target_dt,
        )
        .all()
    )
    return logs

def get_session_activity_logs_for_user_today(
    db: Session,
    user_id: int,
    day_start: datetime,
    day_end: datetime,
) -> List[SessionActivityLog]:
    """
    특정 유저의 오늘 날짜에 해당하는 SessionActivityLog 레코드를 모두 조회합니다
    """
    logs: List[SessionActivityLog] = (
        db.query(SessionActivityLog)
        .join(User, SessionActivityLog.user_id == User.user_id)
        .filter(
            User.user_id == user_id,
            SessionActivityLog.join_at >= day_start,
            SessionActivityLog.join_at < day_end,
        )
        .all()
    )
    return logs

    
# 세션 활동 로그 기록
def create_session_activity_log(db: Session, user: User):
    """
    세션 활동 로그 기록 추가
    """
    log = SessionActivityLog(
        camp_id=user.camp_id,
        user_id=user.user_id,
        date=datetime.utcnow().date(),
        join_at=datetime.utcnow()
    )
    db.add(log)
    db.commit()

    print(f"User {user.user_id} logged in at {log.join_at}")

# 로그아웃 처리
def update_leave_time(db: Session, userId: int):
    """
    로그아웃 처리 + SessionActivityLog 기록 업데이트
    """
    log: SessionActivityLog | None = (
            db.query(SessionActivityLog)
            .filter(SessionActivityLog.user_id == userId)
            .order_by(SessionActivityLog.join_at.desc())
            .first()
        )

    if log and not log.leave_at:
        log.leave_at = datetime.utcnow()
        db.commit()

    print(f"User {userId} logged out at {log.leave_at if log else 'N/A'}")