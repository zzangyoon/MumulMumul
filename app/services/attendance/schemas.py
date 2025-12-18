# =====================================
# 출결 리포트 모델 정의
# =====================================
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

from app.core.mongodb import register_mongo_model


class AttendanceSummary(BaseModel):
    attendance_rate: float
    total_students: int
    high_risk_count: int
    warning_count: int
    late_rate: Optional[float] = None

class AttendanceStudentStat(BaseModel):
    student_id: int
    name: str
    attendance_rate: float
    absent_count: int
    late_count: int
    early_leave_count: int
    pattern_type: Optional[str] = None
    risk_level: Literal["고위험", "위험", "주의", "정상"]
    trend: Optional[float] = None
    ops_action: Optional[str] = None

class AttendanceReport(BaseModel):
    camp_id: int
    camp_name: str
    target_date: datetime

    summary: AttendanceSummary
    students: List[AttendanceStudentStat]

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

# MeetingSummary 모델 등록
register_mongo_model(
    AttendanceReport,
    collection_name="attendance_reports",
    indexes=[
        ("camp_id", 1),
        ("target_date", -1),
        ],
)

# =====================================
# 3-6. 출결 규칙셋 모델 정의
# ====================================


# -----------------------------
# 1) Ruleset Pydantic (최소 필드만)
# -----------------------------
class TimeWindow(BaseModel):
    name: str = "EXCLUDE"
    start: datetime
    end: datetime

class AttendanceRuleset(BaseModel):
    raw_text: str = Field(
        default="",
        description="운영진이 입력한 원본 출결 규칙 텍스트",
    )

    full_day_minutes: int = Field(
        default=480,
        description="하루 출결 인정 기준 총 활동 시간 (분)",
    )

    start_time: datetime = Field(
        default_factory=lambda: datetime(1970, 1, 1, 9, 0),
        description="하루 출결 기준 시작 시간",
    )  # 이후 첫 접속 -> 지각

    end_time: datetime = Field(
        default_factory=lambda: datetime(1970, 1, 1, 18, 0),
        description="하루 출결 기준 종료 시간",
    )  # 이전 마지막 종료 -> 조퇴

    # 점심 시간
    lunch_start: datetime = Field(
        default_factory=lambda: datetime(1970, 1, 1, 12, 0),
        description="점심 시간 시작",
    )
    lunch_end: datetime = Field(
        default_factory=lambda: datetime(1970, 1, 1, 13, 0),
        description="점심 시간 종료",
    )

    # 결석 우선 규칙 (점심 제외 연속 공백)
    absent_if_inactive_gap_minutes_gte: Optional[int] = 240

    # 환산 규칙
    convert_to_absent_late_plus_earlyleave_unit: int = Field(
        default=3,
        description="지각+조퇴 합산 단위 (예: 3회 지각+조퇴 -> 1일 결석 환산)")

    # 수료 기준 (전체 참여일 기준)
    min_attendance_rate_total: float = Field(
        default=0.8,
        description="수료를 위한 최소 출석률 (전체 참여일 기준, 0~1 사이 값)")
    participation_days_weekdays_only: bool = True
    participation_days_exclude_holidays: bool = True

# MeetingSummary 모델 등록
register_mongo_model(
    AttendanceRuleset,
    collection_name="attendance_rulesets",
    indexes=[
        ("id", 1),
        ],
)
