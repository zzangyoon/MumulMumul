# app/services/feedbackBoard/schemas.py
from datetime import datetime
from typing import List, Literal, Optional, Dict, Any
from pydantic import BaseModel, Field
from app.core.mongodb import register_mongo_model

# =====================================
# 피드백 보드 포스트 모델 정의
# =====================================
class FeedbackBoardInsight(BaseModel):
    # --------- 필터링 결과 ---------
    clean_text: Optional[str] = None
    is_active: bool = True
    inactive_reasons: List[str] = Field(default_factory=list)
    duplicate_group_id: Optional[str] = None
    is_group_representative: Optional[bool] = None

    # --------- Split 관련 ---------
    parent_post_id: Optional[str] = None
    is_split_child: Optional[bool] = None
    split_index: Optional[int] = None

    # --------- 분류 결과 ---------
    category: Optional[str] = None              # (<=5, 템플릿 매핑 결과)
    sub_category: Optional[str] = None          # (무제한)
    post_type: Optional[Literal["고민", "건의", "기타"]] = None

    # --------- 위험도 ---------
    is_toxic: Optional[bool] = None
    toxicity_score: Optional[float] = None
    severity: Optional[Literal["low", "medium", "high"]] = None
    sentiment: Optional[str] = None

    # --------- 요약/키워드 ---------
    summary: Optional[str] = None
    keywords: List[str] = Field(default_factory=list)

    # --------- 운영 대응 ---------
    action_type: Optional[Literal["immediate", "short", "long"]] = None

    # --------- 분석 메타 ---------
    analyzed_at: Optional[datetime] = None
    analyzer_version: Optional[str] = None

class FeedbackBoardPost(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    camp_id: int
    author_id: Optional[int] = None
    raw_text: str
    created_at: datetime
    ai_analysis: Optional[FeedbackBoardInsight] = None

# =====================================
# 피드백 보드 주간 리포트 모델 정의
# =====================================
class WeeklyKeyTopic(BaseModel):
    category: str
    count: int
    score: Optional[float] = None  # (요청수+운영중요도+위험도 가중치 산출값, 저장 권장)
    summary: str
    # 원문 전체 대신: post_id 참조 + excerpt/clean_text 일부
    post_ids: List[str] = Field(default_factory=list)
    excerpts: List[str] = Field(default_factory=list)


class WeeklyOpsAction(BaseModel):
    title: str
    target: str
    reason: str
    todo: str
    action_type: Literal["immediate", "short", "long"]


class WeeklyStats(BaseModel):
    total_posts: int
    active_posts: int
    toxic_posts: int
    toxic_ratio: float

    # 위험/주의/보통 (너희 프론트 게이지용과 동일)
    danger_count: int
    warning_count: int
    normal_count: int

    severity_count: Dict[Literal["low", "medium", "high"], int] = Field(default_factory=dict)
    category_count: Dict[str, int] = Field(default_factory=dict)
    sub_category_count: Dict[str, int] = Field(default_factory=dict)

    # 운영 액션 분포
    action_type_count: Dict[Literal["immediate", "short", "long"], int] = Field(default_factory=dict)


class WeeklyWordcloud(BaseModel):
    keywords: List[str] = Field(default_factory=list)


class WeeklyContextSnapshot(BaseModel):
    """
    weekly_report_node에 넣었던 '요약 컨텍스트'를 저장하고 싶을 때만 사용(선택).
    재생성/검증/디버깅에 매우 유용하지만 용량이 커질 수 있음.
    """
    categories: Optional[List[Dict[str, Any]]] = None
    highlights: Optional[List[Dict[str, Any]]] = None


class FeedbackWeeklyReport(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")

    # ---- 식별자 ----
    camp_id: int
    week: Optional[int] = None
    # week 대신 기간 기반 리포트를 만들 수도 있어서 range도 허용
    range_start: Optional[datetime] = None
    range_end: Optional[datetime] = None

    # ---- 생성/버전 관리 ----
    analyzer_version: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    generated_at: Optional[datetime] = None

    # 동일 camp/week 리포트 재생성 시 구분
    run_id: str = Field(default_factory=lambda: f"run_{int(datetime.utcnow().timestamp())}")
    is_final: bool = True                # 운영진 확정본/임시본 구분(선택)
    supersedes_report_id: Optional[str] = None  # 이전 리포트를 대체한 경우

    # ---- 리포트 본문 ----
    week_summary: str
    key_topics: List[WeeklyKeyTopic] = Field(default_factory=list)
    ops_actions: List[WeeklyOpsAction] = Field(default_factory=list)
    stats: WeeklyStats
    wordcloud: WeeklyWordcloud = Field(default_factory=WeeklyWordcloud)

    # ---- 추적/재현성(권장) ----
    # 이 리포트가 어떤 로그들로부터 만들어졌는지 "참조"로 남김
    source_post_ids: List[str] = Field(default_factory=list)
    # 혹은 최소/최대 created_at만 저장해도 됨
    source_min_created_at: Optional[datetime] = None
    source_max_created_at: Optional[datetime] = None

    # 선택: weekly_report_node 입력 컨텍스트 스냅샷(디버깅/감사)
    context_snapshot: Optional[WeeklyContextSnapshot] = None

# =====================================
# MongoDB 모델 등록
# =====================================
register_mongo_model(
    FeedbackBoardPost,
    collection_name="feedback_board_posts",
    indexes=[
        ("camp_id", 1),
        ("created_at", -1)
    ],
)

register_mongo_model(
    FeedbackWeeklyReport,
    collection_name="feedback_weekly_reports",
    indexes=[
        ("camp_id", 1),
        ("week", 1),
    ],
)