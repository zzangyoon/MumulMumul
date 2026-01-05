# app/services/attendance/service.py

from datetime import datetime, timedelta, time, date
from enum import Enum
import json
from typing import List, Dict, Any, Optional

from pydantic import BaseModel
from sqlalchemy.orm import Session
from pymongo.database import Database

from app.core.schemas import Camp, User
from app.services.attendance.nodes.aggregate_attendance_daily import aggregate_attendance_daily
from app.services.attendance.nodes.attendance_insights import generate_attendance_insights
from app.services.attendance.nodes.judge_attendance import judge_attendance_for_students
from app.services.attendance.schemas import AttendanceRuleset, AttendanceResult
from app.services.db_service.attendance_daily import save_attendance_daily
from app.services.db_service.attendance_report import upsert_attendance_report
from app.services.db_service.attendance_ruleset import get_attendance_ruleset
from app.services.db_service.camp import get_camp_by_id, get_students_by_camp
from app.services.db_service.tendency_profiles import get_tendency_profiles_context

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
    
    camp: Camp = get_camp_by_id(db, camp_id)
    students: List[User] = get_students_by_camp(db, camp_id)

    # 2) 날짜 범위
    day_start = camp.start_date.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = target_date.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)

    # 3) ruleset 로딩
    ruleset_doc: AttendanceRuleset | None = get_attendance_ruleset(mongo, camp_id)

    # 4) 성향 분석 JSON 로딩
    tendency_context = get_tendency_profiles_context()

    # # 2) 학생별 출결 판정
    # daily_results: List[AttendanceResult] = judge_attendance_for_students(db, camp_id, day_start, day_end, students, ruleset_doc.compiled_rules if ruleset_doc else None)

    # # 3) 출결 정보 저장
    # save_attendance_daily(db, camp_id, target_date, daily_results)

    # 4) 출결 규칙에 따른 일간 출결 집계
    report = aggregate_attendance_daily(
        db=db,
        camp_id=camp_id,
        camp_name=camp.name,
        start_date=camp.start_date,
        end_date=camp.end_date,
        target_dt=target_date,
        students=students,
        ruleset_doc=ruleset_doc.compiled_rules if ruleset_doc else None,
    )

    # 5) LLM 리포트 작성
    report = generate_attendance_insights(report, tendency_context, ruleset_doc.raw_text if ruleset_doc else "")

    # MongoDB: AttendanceReport upsert
    upsert_attendance_report(report)

    # # F) DM 계획/발송(선택)
    # _plan_and_dispatch_dm(db, camp_id, target_date, report)

    return report
