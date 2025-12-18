# app/services/attendance/service.py

from datetime import datetime, timedelta, time, date
from enum import Enum
import json
from typing import List, Dict, Any, Optional

from pydantic import BaseModel
from sqlalchemy.orm import Session
from pymongo.database import Database

from app.core.schemas import Camp, User
from app.services.attendance.nodes.judge_attendance import judge_attendance_for_students
from app.services.attendance.schemas import AttendanceRuleset
from app.services.db_service.attendance_ruleset import get_attendance_ruleset
from app.services.db_service.camp import get_camp_by_id, get_students_by_camp
from app.services.db_service.session_activity_log import get_session_activity_logs_for_camp_today
from app.services.db_service.tendency_profiles import get_tendency_profiles_context


# ------------------------------------------------------------
# 0) 유틸: 날짜 normalize / 시간 범위
# ------------------------------------------------------------
def _day_range(target_dt: datetime):
    day_start = target_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)
    return day_start, day_end


# ------------------------------------------------------------
# 1) A. 데이터 수집 (Read Model)
#   - students (sqlite)
#   - today session logs (sqlite)
#   - ruleset (mongo)
# ------------------------------------------------------------
class AttendanceContext(BaseModel):
    camp: Camp
    students: List[User]
    day_start: datetime
    day_end: datetime
    ruleset_doc: AttendanceRuleset | None
    tendency_context: str   

def _load_context(
    db: Session,
    mongo: Database,
    camp_id: int,
    target_dt: datetime,
) -> AttendanceContext:
    # 1) 캠프 / 학생 조회
    camp: Camp = get_camp_by_id(db, camp_id)
    students: List[User] = get_students_by_camp(db, camp_id)

    # 2) 날짜 범위
    day_start = target_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)

    # 3) ruleset 로딩
    ruleset_doc: AttendanceRuleset | None = get_attendance_ruleset(camp_id)

    # 4) 성향 분석 JSON 로딩
    tendency_context = get_tendency_profiles_context()

    return AttendanceContext(
        camp=camp,
        students=students,
        day_start=day_start,
        day_end=day_end,
        ruleset_doc=ruleset_doc,
        tendency_context=tendency_context,
    )

# ------------------------------------------------------------
# 3) B. 규칙 엔진 (결정론)
#   - session_activity_log에서 피처 계산
#   - compiled_rules 적용해서 attendance_type 결정
#   - (중요) 결과는 session_activity_log + daily_aggregate 저장에 쓰임
# ------------------------------------------------------------

# ------------------------------------------------------------
# 4) C. 저장 레이어 (Write Model)
#   - session_activity_log: attendance_type, attendance_date, ruleset_id 업데이트
#   - attendance_daily_aggregate: upsert
# ------------------------------------------------------------
def _persist_daily_results(
    db: Session,
    camp_id: int,
    target_dt: datetime,
    ruleset_id: str,
    results: List[Dict[str, Any]],
):
    """
    results item 예:
      {
        "student_id": 123,
        "attendance_type": "...",
        "active_minutes": ...,
        "max_inactive_gap_minutes": ...,
      }
    """

    # day = target_dt.date()

    # for each result:
    #   1) session_activity_log 업데이트
    #      - 해당 학생의 "오늘" 로그들에 attendance_type, attendance_date, ruleset_id set
    #      - 로그가 없으면? (absence는 로그가 없으니 session_activity_log 업데이트는 스킵)
    #
    #   2) attendance_daily_aggregate upsert
    #      - (camp_id, student_id, date) unique
    #      - attendance_type 저장
    #      - active_minutes/max_gap 저장 (없으면 null)

    # db.commit()
    return


# ------------------------------------------------------------
# 5) D. 리포트 계산 레이어 (Skeleton Report)
#   - attendance_daily_aggregate 기반으로 누적 카운트/출석률 계산
#   - "전체 참여일" = 주말/공휴일 제외 평일만
# ------------------------------------------------------------
def _build_skeleton_report(
    db: Session,
    camp_id: int,
    camp_name: str,
    target_dt: datetime,
    students: List[Any],
):
    """
    return AttendanceReport (students: 기본 통계만 채움)
    """

    # 1) 캠프 시작일~target_dt 범위 구함 (camp.start_date 필요)
    # start = camp.start_date
    # end = target_dt.date()

    # 2) 참여일(business days) 계산
    # - weekday only (Mon-Fri)
    # - 공휴일 제외: (나중에 holiday source 연결)
    # total_participation_days = ...

    # 3) 각 학생별 누적 집계
    # - attendance_daily_aggregate에서 date<=target_dt의 기록 가져옴
    # - absent_count / late_count / early_leave_count 계산
    # - attendance_rate = present_days / total_participation_days
    #
    # 주의: present_days 계산할 때 LATE/EARLY_LEAVE를 출석으로 포함할지 정책 필요
    # 지금은: PRESENT/LATE/EARLY_LEAVE 모두 "참여"로 잡는 식이 현실적

    # 4) summary 계산
    # attendance_rate (전체 평균)
    # total_students
    # high_risk_count/warning_count는 아직 0 (LLM 전)
    # late_rate = late_students / total_students

    # 5) AttendanceReport 객체 생성 (ruleset_id도 넣기)
    report = None
    return report


# ------------------------------------------------------------
# 6) E. LLM 인사이트 레이어
#   - 학생별 risk/pattern/trend/ops_action 채움
#   - (이번 단계에서는 의사코드만)
# ------------------------------------------------------------
def _enrich_report_with_llm(
    report: Any,
    tendency_context: str,
    students: List[Any],
):
    # for each student stat:
    #   - 입력: stat + 성향 + 최근 n일 피처 요약
    #   - 출력: risk_level, pattern_type, trend, ops_action
    # report.summary.high_risk_count, warning_count 갱신
    return report


# ------------------------------------------------------------
# 7) F. DM 자동화 레이어
#   - DM 대상자 선정 -> 메시지 생성 -> dispatch 로그 저장
# ------------------------------------------------------------
def _plan_and_dispatch_dm(
    db: Session,
    camp_id: int,
    target_dt: datetime,
    report: Any,
):
    # 1) 대상자 선정:
    #   - 오늘 LATE/EARLY_LEAVE/ABSENT
    #   - risk_level 고위험/위험
    #   - 연속 n일 공백(추가 규칙)
    #
    # 2) 각 대상자별 메시지 생성(LLM) - 성향 기반
    # 3) attendance_dm_dispatch에 PLANNED로 저장
    # 4) tool 실행(send_dm)하고 SENT/FAILED 업데이트
    return


# ------------------------------------------------------------
# 메인 엔트리: generate_attendance_report
# ------------------------------------------------------------
def generate_attendance_report(
    camp_id: int,
    target_date: datetime,
    db: Session,
    mongo: Database,
):
    """
    최종 흐름(한 번에 끝)
    A) context 로딩
    B) ruleset 컴파일 보장
    B-2) 학생별 판정
    C) DB 저장
    D) skeleton report 생성
    E) LLM 인사이트 채움
    - mongo AttendanceReport 업서트
    F) DM 계획/발송
    """

    # A) context
    context: AttendanceContext = _load_context(db, mongo, camp_id, target_date)

    camp = context.camp
    students = context.students
    day_start = context.day_start
    day_end = context.day_end
    ruleset_doc = context.ruleset_doc
    compiled_rules = ruleset_doc.get("compiled_rules") if ruleset_doc else {}
    tendency_context = context.tendency_context

    # B-2) 학생별 판정
    daily_attendances = judge_attendance_for_students(db, camp_id, day_start, day_end, ruleset_doc)

    # C) 저장
    ruleset_id = str(ruleset_doc.get("_id")) if ruleset_doc else None
    _persist_daily_results(db, camp_id, target_date, ruleset_id, daily_results)

    # D) skeleton report
    report = _build_skeleton_report(
        db=db,
        camp_id=camp_id,
        camp_name=camp.name,
        target_dt=target_date,
        students=students,
    )
    # report.ruleset_id = ruleset_id

    # E) LLM 인사이트(선택)
    # t
    report = _enrich_report_with_llm(report, tendency_context, students)

    # MongoDB: AttendanceReport upsert
    # upsert_attendance_report(mongo, report)

    # F) DM 계획/발송(선택)
    _plan_and_dispatch_dm(db, camp_id, target_date, report)

    return report
