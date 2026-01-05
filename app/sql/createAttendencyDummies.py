# app/sql/createAttendanceReportDummies.py

import sys
from pathlib import Path
from datetime import datetime, timedelta, time, date

# 이 파일 기준으로 프로젝트 루트 계산
CURRENT_FILE = Path(__file__).resolve()
ROOT_DIR = CURRENT_FILE.parents[2]   # .../MumulMumul
sys.path.append(str(ROOT_DIR))

from typing import Dict, Tuple, List, Optional

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


def to_attendance_letter(attendance_type: str) -> str:
    """
    최근 30일 요약용 P/L/E/A 변환
    """
    mapping = {
        "PRESENT": "P",
        "LATE": "L",
        "EARLY_LEAVE": "E",
        "ABSENT": "A",
        "UNKNOWN": "U",
    }
    return mapping.get(attendance_type, "U")


def calc_rate_for_last_n(flags: List[int], n: int) -> Optional[float]:
    """
    flags: 1(출석), 0(결석) 리스트 (days_until_now 기준 순서)
    """
    if not flags:
        return None
    window = flags[-n:] if len(flags) >= n else flags
    return (sum(window) / len(window)) if window else None


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

    if len(users) != len(login_ids):
        missing = [lid for lid in login_ids if lid not in [u.login_id for u in users]]
        print(f"⚠ 일부 유저를 찾지 못했습니다: {missing} (그래도 있는 유저로만 진행)")

    if not users:
        print("❌ 리포트 생성 대상 유저가 없습니다.")
        return []

    target_user_ids = [u.user_id for u in users]

    # 해당 캠프 기간의 출결 로그 전체 로드
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
        unknown_count = 0

        students_stats = []

        for i, u in enumerate(users):
            uid = u.user_id

            attend_days = 0
            absent_days = 0
            late_count = 0
            early_leave_count = 0

            # 연속 결석 / 연속 지각 (target_d 기준 "최근 연속")
            current_absent_streak = 0
            current_late_streak = 0

            max_absent_streak = 0

            # 최근 n일 계산용
            daily_attend_flags: List[int] = []   # 1: 출석, 0: 결석
            daily_types: List[str] = []          # "PRESENT/LATE/EARLY_LEAVE/ABSENT"

            # 날짜별 출결 기록(요약용)
            attendance_records: List[Dict[str, str]] = []

            for d in days_until_now:
                day_log_list = logs_by_user_date.get((uid, d), [])

                if not day_log_list:
                    # 결석
                    absent_days += 1
                    daily_attend_flags.append(0)
                    daily_types.append("ABSENT")
                    attendance_records.append(
                        {"date": d.isoformat(), "attendance_type": "ABSENT"}
                    )

                    current_absent_streak += 1
                    max_absent_streak = max(max_absent_streak, current_absent_streak)

                    # 지각 연속은 끊김
                    current_late_streak = 0
                    continue

                # 출석 (여러 개 로그가 있어도 첫 번째 join, 마지막 leave 기준)
                day_log_list_sorted = sorted(day_log_list, key=lambda x: x.join_at)
                first_log = day_log_list_sorted[0]
                last_log = sorted(day_log_list, key=lambda x: (x.leave_at or x.join_at))[-1]

                attend_days += 1
                total_present += 1
                daily_attend_flags.append(1)
                current_absent_streak = 0  # 결석 연속 끊김

                total_logs += 1

                join_t = first_log.join_at.time()
                leave_t = last_log.leave_at.time() if last_log.leave_at else None

                # 일별 출결 타입 결정 (우선순위: ABSENT는 위에서 처리)
                # 여기서는 "지각"을 우선으로 두고, 지각 아니면 조퇴 판정
                day_type = "PRESENT"

                if join_t > LATE_THRESHOLD:
                    day_type = "LATE"
                    late_count += 1
                    total_late += 1
                    current_late_streak += 1
                else:
                    current_late_streak = 0

                if day_type == "PRESENT" and leave_t and leave_t < EARLY_LEAVE_THRESHOLD:
                    day_type = "EARLY_LEAVE"
                    early_leave_count += 1

                daily_types.append(day_type)
                attendance_records.append(
                    {"date": d.isoformat(), "attendance_type": day_type}
                )

            # 개인 출석률
            attendance_rate = attend_days / n_days if n_days > 0 else 0.0

            # 최근 30일 “P/L/E/A” 요약
            last_30_types = daily_types[-30:] if daily_types else []
            recent_30_attendance_summary = "".join(to_attendance_letter(t) for t in last_30_types) if last_30_types else None

            # consecutive_absent_days / consecutive_late_days (target_d 기준)
            # 현재 streak 값이 "마지막 날 기준"으로 유지됨
            consecutive_absent_days = current_absent_streak
            consecutive_late_days = current_late_streak

            # 최근 7/14/30 출석률
            attendance_rate_7d = calc_rate_for_last_n(daily_attend_flags, 7)
            attendance_rate_14d = calc_rate_for_last_n(daily_attend_flags, 14)
            attendance_rate_30d = calc_rate_for_last_n(daily_attend_flags, 30)

            # 트렌드(최근 5일 vs 직전 5일 출석률 차이)
            trend_value = 0.0
            if len(daily_attend_flags) >= 6:
                last5 = daily_attend_flags[-5:]
                prev5 = daily_attend_flags[-10:-5] if len(daily_attend_flags) >= 10 else daily_attend_flags[:-5]
                if prev5:
                    last5_rate = sum(last5) / len(last5)
                    prev5_rate = sum(prev5) / len(prev5)
                    trend_value = last5_rate - prev5_rate

            # unknown (한 번도 참여 기록이 없는 경우)
            never_joined = (attend_days == 0)
            if never_joined:
                unknown_count += 1

            # 리스크 레벨 간단 규칙 (더미용)
            if never_joined:
                risk_level = "미확인"
            elif attendance_rate < 0.5 or max_absent_streak >= 3:
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

            # pattern_type (스키마 허용값으로 매핑)
            if n_days <= 3:
                pattern_type = "신규"
            elif never_joined:
                pattern_type = "데이터없음"
            elif max_absent_streak >= 3:
                pattern_type = "공백위험형"
            elif absent_days / n_days >= 0.5:
                pattern_type = "결석형"
            elif late_count >= max(2, int(attend_days * 0.4)) if attend_days > 0 else False:
                pattern_type = "지각형"
            elif early_leave_count >= max(2, int(attend_days * 0.4)) if attend_days > 0 else False:
                pattern_type = "조퇴형"
            elif attendance_rate >= 0.95 and late_count == 0 and absent_days == 0:
                pattern_type = "안정형"
            else:
                pattern_type = "불규칙형"

            # 운영진 액션 더미
            if risk_level == "고위험":
                ops_action = "개인 면담 및 학습 계획 재점검 필요"
            elif risk_level == "위험":
                ops_action = "출석/과제 현황 점검 및 개별 메시지 발송"
            elif risk_level == "주의":
                ops_action = "안부 확인 및 참여 독려 메시지 권장"
            elif risk_level == "미확인":
                ops_action = "초기 참여 유도 및 접속 환경 점검 안내"
            else:
                ops_action = "별도 조치 필요 없음"

            priority_order = ["pillar", "doer", "analyst", "supporter", "balancer"]
            students_stats.append(
                {
                    "user_id": uid,
                    "name": u.name,
                    "attendance_rate": attendance_rate,
                    "absent_count": absent_days,
                    "late_count": late_count,
                    "early_leave_count": early_leave_count,

                    # optional
                    "personality_type": priority_order[i],

                    # 추가 필드들
                    "attendance_records": attendance_records,
                    "recent_30_attendance_summary": recent_30_attendance_summary,
                    "consecutive_absent_days": consecutive_absent_days,
                    "consecutive_late_days": consecutive_late_days,
                    "attendance_rate_7d": attendance_rate_7d,
                    "attendance_rate_14d": attendance_rate_14d,
                    "attendance_rate_30d": attendance_rate_30d,

                    # enums
                    "risk_level": risk_level,
                    "pattern_type": pattern_type,

                    # trend must be float in schema (default 0.0)
                    "trend": float(trend_value) if trend_value is not None else 0.0,

                    "ops_action": ops_action,
                }
            )

        # 리포트 summary
        camp_total_students = len(users)
        total_possible_attend = camp_total_students * n_days
        overall_attendance_rate = (
            total_present / total_possible_attend if total_possible_attend > 0 else 0.0
        )

        # late_rate: "출석한 로그 기준 지각 비율" (없으면 None)
        late_rate = (total_late / total_logs) if total_logs > 0 else None

        report_doc = {
            "camp_id": camp.camp_id,
            "camp_name": camp.name,

            # target_date는 datetime으로 (자정 기준)
            "target_date": datetime.combine(target_d, time(0, 0, 0)),

            "summary": {
                "attendance_rate": overall_attendance_rate,
                "total_students": camp_total_students,
                "late_rate": late_rate,
                "high_risk_count": high_risk_count,
                "warning_count": warning_count,
                "unknown_count": unknown_count,
            },

            # ✅ 스키마에 맞게 students_stat
            "students_stat": students_stats,

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
