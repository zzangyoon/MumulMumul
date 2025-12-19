import sys
from pathlib import Path

# 프로젝트 루트 설정
CURRENT_FILE = Path(__file__).resolve()
ROOT_DIR = CURRENT_FILE.parents[2]
sys.path.append(str(ROOT_DIR))

import random
from datetime import datetime, timedelta, time, date

from sqlalchemy.orm import Session

from app.core.db import SessionLocal  # 프로젝트에 맞게
from app.core.schemas import SessionActivityLog  # 프로젝트에 맞게


CAMP_ID = 1
START_DATE = date(2025, 11, 3)
END_DATE = date(2025, 12, 15)

# 유저 id (너가 준 값)
USERS = {
    5: "user1",  # 김해찬
    6: "user2",  # 윤여민
    7: "user3",  # 김서영
    8: "user4",  # 이성윤
    9: "user5",  # 차요준
}

random.seed(42)


def iter_weekdays(start: date, end: date):
    cur = start
    while cur <= end:
        if cur.weekday() < 5:  # 0~4 = Mon~Fri
            yield cur
        cur += timedelta(days=1)


def dt(d: date, hh: int, mm: int = 0) -> datetime:
    return datetime(d.year, d.month, d.day, hh, mm, 0)


def add_log(db: Session, user_id: int, d: date, join_h: int, join_m: int, leave_h: int, leave_m: int):
    row = SessionActivityLog(
        camp_id=CAMP_ID,
        user_id=user_id,
        date=d,
        join_at=dt(d, join_h, join_m),
        leave_at=dt(d, leave_h, leave_m),
    )
    db.add(row)


def seed():
    db = SessionLocal()
    try:
        weekdays = list(iter_weekdays(START_DATE, END_DATE))
        n = len(weekdays)

        for idx, d in enumerate(weekdays):
            # -------------------------
            # user1: 안정형 (거의 정상)
            # -------------------------
            if random.random() < 0.95:
                add_log(db, 5, d, 9, random.choice([0, 0, 5, 10]), 18, random.choice([0, 0, 0, 10]))
            else:
                # 아주 가끔 조퇴
                add_log(db, 5, d, 9, 0, 16, 30)

            # -------------------------
            # user2: 지각형 + 점점 악화
            # 초반: 09:00 근처 / 후반: 10:30까지 밀림
            # -------------------------
            # 지각 분(min) = 주차 진행될수록 커짐
            late_min = int((idx / max(1, n - 1)) * 90)  # 0~90분
            join = dt(d, 9, 0) + timedelta(minutes=late_min + random.choice([0, 0, 5, 10]))
            leave = dt(d, 18, 0)
            if random.random() < 0.1:  # 가끔 조퇴도 섞기
                leave = dt(d, 17, 0)
            add_log(db, 6, d, join.hour, join.minute, leave.hour, leave.minute)

            # -------------------------
            # user3: 결석형 + 최근 급락
            # 마지막 2주(10일 내외) 결석 폭증
            # -------------------------
            last_two_weeks = idx >= n - 10
            if last_two_weeks:
                # 최근 급락: 60% 결석
                if random.random() < 0.6:
                    pass  # 결석 = 로그 없음
                else:
                    add_log(db, 7, d, 9, 30, 18, 0)  # 지각 약간
            else:
                # 초반: 대부분 정상 + 가끔 결석(10%)
                if random.random() < 0.1:
                    pass
                else:
                    add_log(db, 7, d, 9, 0, 18, 0)

            # -------------------------
            # user4: 조퇴형 + 회복
            # 초반엔 16~17시 조퇴 많고, 후반엔 18시 근접
            # -------------------------
            # 조퇴 정도: 초반(많이) -> 후반(적게)
            early_leave_min = int((1 - (idx / max(1, n - 1))) * 120)  # 120분(2h) -> 0
            leave_time = dt(d, 18, 0) - timedelta(minutes=early_leave_min + random.choice([0, 0, 10, 20]))
            join_time = dt(d, 9, 0)
            if random.random() < 0.15:
                # 가끔 지각
                join_time = dt(d, 9, 20)
            add_log(db, 8, d, join_time.hour, join_time.minute, leave_time.hour, leave_time.minute)

            # -------------------------
            # user5: 공백위험형/불규칙형
            # 하루 2세션으로 점심 제외 4h+ 공백을 일부 날짜에 만들어줌
            # + 가끔 결석
            # -------------------------
            if random.random() < 0.15:
                pass  # 결석
            else:
                if random.random() < 0.6:
                    # 공백위험: 오전 조금 접속 -> 오후 늦게 다시 접속
                    # 예: 09:30~11:00, 15:30~18:00  (gap=4h30m, 점심 제외해도 3h30m지만 날짜마다 더 크게)
                    add_log(db, 9, d, 9, 30, 10, 30)
                    add_log(db, 9, d, 16, 0, 18, 0)   # gap 크게
                else:
                    # 불규칙: 늦게 시작하거나 짧게 접속
                    if random.random() < 0.5:
                        add_log(db, 9, d, 10, 0, 18, 0)  # 지각
                    else:
                        add_log(db, 9, d, 9, 0, 15, 0)   # 조퇴

        db.commit()
        print("✅ session_activity_log seeded")

    finally:
        db.close()


if __name__ == "__main__":
    seed()
