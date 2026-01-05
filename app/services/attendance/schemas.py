# =====================================
# 출결 리포트 모델 정의
# =====================================
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

from app.core.mongodb import register_mongo_model
from app.core.schemas import AttendanceType

class AttendanceFeature(BaseModel):
    total_active_time: Optional[int] = None
    first_join: Optional[datetime] = None
    last_leave: Optional[datetime] = None
    never_joined: Optional[bool] = None

class AttendanceResult(BaseModel):
    user_id: int
    attendance_type: AttendanceType = "UNKNOWN"
    features: AttendanceFeature | None = None
    is_finalized: bool = False  # 최종 확정 여부

class AttendanceSummary(BaseModel):
    attendance_rate: float
    total_students: int
    late_rate: float = None
    high_risk_count: Optional[int] = None
    warning_count: Optional[int] = None
    unknown_count: Optional[int] = None

class AttendanceStudentStat(BaseModel):
    user_id: int
    name: str
    attendance_rate: float
    absent_count: int
    late_count: int
    early_leave_count: int
    personality_type: str = None
    attendance_records: List[Dict[str, str]] = None  # 날짜별 출결유형 요약
    recent_30_attendance_summary: str = None  # 최근 30일 “P/L/E/A” 요약,
    consecutive_absent_days: int = None,
    consecutive_late_days: int = None,
    attendance_rate_7d: float = None,
    attendance_rate_14d: float = None,
    attendance_rate_30d: float = None,

    risk_level: Literal[
        "고위험",
        "위험",
        "주의",
        "정상",
        "미확인",
    ] = Field(
        description="학생의 출결 위험 수준",
        default="미확인",
    )

    pattern_type: Literal[
        "안정형",
        "지각형",
        "조퇴형",
        "결석형",
        "불규칙형",
        "공백위험형",
        "신규",
        "데이터없음",
    ] = Field(
        description="학생의 주요 출결 패턴 유형",
        default="데이터없음",
    )

    trend: float = Field(
        description=(
            "최근 출결 추세 변화 값. "
            "양수는 개선(+), 음수는 악화(-), 0에 가까울수록 변화 없음. "
            "예: -0.25, 0.1"
        ),
        default=0.0,
    )

    ops_action: str = Field(
        description="운영진이 취해야 할 권장 조치 또는 커뮤니케이션 가이드",
        default="",
    )

class AttendanceReport(BaseModel):
    camp_id: int
    camp_name: str
    target_date: datetime

    summary: AttendanceSummary
    students_stat: List[AttendanceStudentStat]

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
class CompileRuleset(BaseModel):
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

class AttendanceRuleset(BaseModel):
    ruleset_id: str
    camp_id: int
    raw_text: str
    compiled_rules: CompileRuleset
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

# MeetingSummary 모델 등록
register_mongo_model(
    AttendanceRuleset,
    collection_name="attendance_ruleset",
    indexes=[
        ("id", 1),
        ],
)
