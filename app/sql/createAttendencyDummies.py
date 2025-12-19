# app/sql/createAttendanceReportDummies.py

import sys
from pathlib import Path
from datetime import datetime, timedelta, time, date

# 이 파일 기준으로 프로젝트 루트 계산
CURRENT_FILE = Path(__file__).resolve()
ROOT_DIR = CURRENT_FILE.parents[2]   # .../MumulMumul
sys.path.append(str(ROOT_DIR))

from typing import Dict, Tuple, List

from pymongo import MongoClient
from sqlalchemy.orm import sessionmaker

from app.core.schemas import User, Camp, SessionActivityLog, init_db
from app.config import SQLITE_URL, MONGO_URL, MONGO_DB_NAME


# ---------------------------
# 유틸: 날짜 범위 (date 기준)
# ---------------------------
def daterange(start: date, end: date):
    """날짜 범위 생성기 (start~end inclusive, date 객체)"""
    for n in range((end - start).days + 1):
        yield start + timedelta(days=n)


# ---------------------------
# 리포트 생성 로직
# ---------------------------

def build_attendance_reports_for_camp(session, camp: Camp) -> List[Dict]:
    """
    주어진 Camp에 대해, 캠프 기간 동안의 날짜별 AttendanceReport 더미 생성.
    반환값: AttendanceReport dict 리스트 (몽고에 바로 insert 가능한 형태)
    """
    # 캠프 기간을 date 타입으로 정규화
    if isinstance(camp.start_date, datetime):
        start_d = camp.start_date.date()
    else:
        start_d = camp.start_date

    if isinstance(camp.end_date, datetime):
        end_d = camp.end_date.date()
    else:
        end_d = camp.end_date

    # 출결 패턴 더미가 있는 user1~user5만 대상으로 리포트 생성
    login_ids = ["user1", "user2", "user3", "user4", "user5"]
    users: List[User] = (
        session.query(User)
        .filter(User.login_id.in_(login_ids))
        .all()
    )
    user_by_id: Dict[int, User] = {u.user_id: u for u in users}

    if len(users) != len(login_ids):
        missing = [lid for lid in login_ids if lid not in [u.login_id for u in users]]
        print(f"⚠ 일부 유저를 찾지 못했습니다: {missing} (그래도 있는 유저로만 진행)")
    
    if not users:
        print("❌ 리포트 생성 대상 유저가 없습니다.")
        return []

    target_user_ids = [u.user_id for u in users]

    # 해당 캠프 기간의 출결 로그 전체 로드
    # (캠프 날짜 기준 00:00 ~ 마지막 날 다음날 00:00)
    start_dt = datetime.combine(start_d, time(0, 0, 0))
    end_dt_exclusive = datetime.combine(end_d + timedelta(days=1), time(0, 0, 0))

    logs: List[SessionActivityLog] = (
        session.query(SessionActivityLog)
        .filter(
            SessionActivityLog.user_id.in_(target_user_ids),
            SessionActivityLog.join_at >= start_dt,
            SessionActivityLog.join_at < end_dt_exclusive,
        )
        .all()
    )

    # (user_id, date) 단위로 로그 묶기
    logs_by_user_date: Dict[Tuple[int, date], List[SessionActivityLog]] = {}
    for log in logs:
        log_date = log.join_at.date()
        key = (log.user_id, log_date)
        logs_by_user_date.setdefault(key, []).append(log)

    all_dates = list(daterange(start_d, end_d))
    reports: List[Dict] = []

    # 지각 / 조퇴 기준 (더미용 간단 규칙)
    LATE_THRESHOLD = time(9, 10)
    EARLY_LEAVE_THRESHOLD = time(18, 0)

    # 날짜별 리포트 생성
    for target_d in all_dates:
        days_until_now = [d for d in all_dates if d <= target_d]
        n_days = len(days_until_now)
        if n_days == 0:
            continue

        total_present = 0
        total_logs = 0
        total_late = 0

        high_risk_count = 0
        warning_count = 0

        students_stats = []

        for u in users:
            uid = u.user_id

            attend_days = 0
            absent_days = 0
            late_count = 0
            early_leave_count = 0

            # 연속 결석 패턴을 보기 위한 값
            current_absent_streak = 0
            max_absent_streak = 0

            # 후반부 트렌드 계산용: 최근 5일 vs 그 이전 5일
            daily_attend_flags = []  # 1: 출석, 0: 결석

            for d in days_until_now:
                day_log_list = logs_by_user_date.get((uid, d), [])
                if not day_log_list:
                    # 결석
                    absent_days += 1
                    current_absent_streak += 1
                    max_absent_streak = max(max_absent_streak, current_absent_streak)
                    daily_attend_flags.append(0)
                    continue

                # 출석 (여러 개 로그가 있어도 첫 번째만 기준으로)
                log = sorted(day_log_list, key=lambda x: x.join_at)[0]
                attend_days += 1
                total_present += 1
                daily_attend_flags.append(1)
                current_absent_streak = 0  # 연속 결석 끊김

                total_logs += 1

                join_t = log.join_at.time()
                leave_t = log.leave_at.time() if log.leave_at else None

                if join_t > LATE_THRESHOLD:
                    late_count += 1
                    total_late += 1

                if leave_t and leave_t < EARLY_LEAVE_THRESHOLD:
                    early_leave_count += 1

            # 개인 출석률
            attendance_rate = attend_days / n_days if n_days > 0 else 0.0

            # 트렌드(최근 5일 vs 직전 5일 출석률 차이)
            trend_value = None
            if len(daily_attend_flags) >= 6:
                last5 = daily_attend_flags[-5:]
                prev5 = daily_attend_flags[-10:-5] if len(daily_attend_flags) >= 10 else daily_attend_flags[:-5]

                if prev5:
                    last5_rate = sum(last5) / len(last5)
                    prev5_rate = sum(prev5) / len(prev5)
                    trend_value = last5_rate - prev5_rate

            # 리스크 레벨 간단 규칙 (더미용)
            # - 출석률과 연속 결석일수를 조합해서 분류
            if attendance_rate < 0.5 or max_absent_streak >= 3:
                risk_level = "고위험"
            elif attendance_rate < 0.7 or max_absent_streak == 2:
                risk_level = "위험"
            elif attendance_rate < 0.9:
                risk_level = "주의"
            else:
                risk_level = "정상"

            if risk_level == "고위험":
                high_risk_count += 1
            if risk_level in ("위험", "주의"):
                warning_count += 1

            # 패턴 타입 (대략적인 라벨)
            if attendance_rate > 0.95 and late_count == 0:
                pattern_type = "꾸준한 정상 출석"
            elif max_absent_streak >= 3:
                pattern_type = "장기 결석 패턴"
            elif late_count > attend_days / 2 if attend_days > 0 else False:
                pattern_type = "지각 잦은 패턴"
            else:
                pattern_type = "불규칙 출석 패턴"

            # 운영진 액션 더미
            if risk_level == "고위험":
                ops_action = "개인 면담 및 학습 계획 재점검 필요"
            elif risk_level == "위험":
                ops_action = "출석/과제 현황 점검 및 개별 메시지 발송"
            elif risk_level == "주의":
                ops_action = "안부 확인 및 참여 독려 메시지 권장"
            else:
                ops_action = "별도 조치 필요 없음"

            students_stats.append(
                {
                    "user_id": uid,
                    "name": u.name,
                    "attendance_rate": attendance_rate,
                    "absent_count": absent_days,
                    "late_count": late_count,
                    "early_leave_count": early_leave_count,
                    "pattern_type": pattern_type,
                    "risk_level": risk_level,
                    "trend": trend_value,
                    "ops_action": ops_action,
                }
            )

        # 리포트 summary
        camp_total_students = len(users)
        total_possible_attend = camp_total_students * n_days
        overall_attendance_rate = (
            total_present / total_possible_attend if total_possible_attend > 0 else 0.0
        )
        late_rate = total_late / total_logs if total_logs > 0 else None

        report_doc = {
            "camp_id": camp.camp_id,
            "camp_name": camp.name,
            # target_date는 datetime으로 (자정 기준)
            "target_date": datetime.combine(target_d, time(0, 0, 0)),

            "summary": {
                "attendance_rate": overall_attendance_rate,
                "total_students": camp_total_students,
                "high_risk_count": high_risk_count,
                "warning_count": warning_count,
                "late_rate": late_rate,
            },
            "students": students_stats,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }

        reports.append(report_doc)

    return reports


# ---------------------------
# 메인: 몽고에 insert
# ---------------------------

def seed_attendance_reports():
    # 1) SQLite 세션
    engine = init_db(SQLITE_URL)
    Session = sessionmaker(bind=engine, autoflush=False)
    session = Session()

    # 2) Mongo 클라이언트
    mongo_client = MongoClient(MONGO_URL)
    mongo_db = mongo_client[MONGO_DB_NAME]
    collection = mongo_db["attendance_reports"]

    try:
        # 머물머물 캠프 찾기
        camp: Camp | None = (
            session.query(Camp)
            .filter(Camp.name == "머물머물 캠프")
            .first()
        )
        if camp is None:
            print("❌ '머물머물 캠프'를 찾을 수 없습니다. 먼저 캠프 더미 데이터를 생성했는지 확인하세요.")
            return

        print(f"🚀 '{camp.name}' 캠프의 출결 리포트 더미 생성 시작...")

        # 기존 리포트 삭제하고 싶으면 아래 주석 해제
        # collection.delete_many({"camp_id": camp.camp_id})
        # print("🧹 기존 attendance_reports 문서 삭제 완료")

        reports = build_attendance_reports_for_camp(session, camp)

        if not reports:
            print("⚠ 생성된 리포트가 없습니다.")
            return

        collection.insert_many(reports)
        print(f"✅ attendance_reports에 {len(reports)}개 리포트 더미 생성 완료!")

    finally:
        session.close()
        mongo_client.close()


if __name__ == "__main__":
    seed_attendance_reports()
