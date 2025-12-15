# app/services/feedbackBoard/io_contract.py
from __future__ import annotations

from typing import Optional, Literal, List, Dict, Any, Tuple
from datetime import datetime
from pydantic import BaseModel, Field

from app.services.feedbackBoard.schemas import FeedbackBoardPost


# ----------------------------
# 1) Pipeline Input / Config
# ----------------------------

class DateRange(BaseModel):
    start: datetime
    end: datetime


class RunConfig(BaseModel):
    camp_id: int
    week: Optional[int] = None
    range: Optional[DateRange] = None

    analyzer_version: str = "fb_v1"

    # 정책 파라미터(결정된 값 반영)
    split_max_parts: int = 5
    dedup_similarity_threshold: float = 0.5
    dedup_scope: Literal["user_week"] = "user_week"

    # 카테고리 템플릿 (운영진 제공)
    # 예: ["팀 갈등", "일정 압박", "과제 난이도", "운영/행정", "피로/번아웃"]
    category_template: List[str] = Field(default_factory=list)


class PipelineInput(BaseModel):
    config: RunConfig


# ----------------------------
# 2) Intermediate Aggregations
# ----------------------------

class ClusterItem(BaseModel):
    local_cluster_id: int
    sub_category: str
    # 대표 문장/요약 (weekly context용)
    representative_summary: str
    representative_keywords: List[str] = Field(default_factory=list)
    count: int
    action_type: Optional[Literal["immediate", "short", "long"]] = None,
    post_ids: List[str] = Field(default_factory=list)


class CategoryAgg(BaseModel):
    category: str
    count: int
    sub_items: List[ClusterItem] = Field(default_factory=list)


class RiskAgg(BaseModel):
    total: int
    toxic_count: int
    severity_count: Dict[Literal["low", "medium", "high"], int]
    danger_count: int         # (is_toxic OR severity=high)
    warning_count: int        # (severity=medium AND not toxic)
    normal_count: int


class RiskHighlight(BaseModel):
    post_id: str
    created_at: datetime
    author_id: Optional[int]
    category: Optional[str]
    sub_category: Optional[str]
    severity: Optional[str]
    is_toxic: Optional[bool]
    summary: Optional[str]
    excerpt: Optional[str] = None

class KeyTopicCandidate(BaseModel):
    """
    Top3 후보
    """
    category: str
    count: int
    sub_category: Optional[str] = None

    representative_summary: str
    representative_keywords: List[str] = Field(default_factory=list)

    post_ids: List[str] = Field(default_factory=list)
    excerpts: List[str] = Field(default_factory=list)

    score: float = 0.0  # (요청수+운영중요도+위험도 가중치) 산출값 저장용

class OpsActionCandidate(BaseModel):
    """
    운영 개입 가이드 후보
    """
    title: str
    target: str
    reason: str
    action_type: Literal["immediate", "short", "long"]
    related_post_ids: List[str] = Field(default_factory=list)
    related_excerpts: List[str] = Field(default_factory=list)

class WeeklyContext(BaseModel):
    camp_id: int
    week: Optional[int] = None
    range: Optional[DateRange] = None

    risk: RiskAgg
    categories: List[CategoryAgg] = Field(default_factory=list)
    highlights: List[RiskHighlight] = Field(default_factory=list)
    action_type_count: Dict[Literal["immediate", "short", "long"], int] = Field(default_factory=dict)

    key_topic_candidates: List[KeyTopicCandidate] = Field(default_factory=list)  # Top3 후보
    ops_action_candidates: List[OpsActionCandidate] = Field(default_factory=list)  # ops 후보(보통 3개)

# ----------------------------
# 3) Weekly Report Outputs
# ----------------------------

from typing import List, Dict, Any, Literal
from pydantic import BaseModel, Field


from typing import List, Dict, Any, Literal
from pydantic import BaseModel, Field


class KeyTopic(BaseModel):
    category: str = Field(
        ...,
        description=(
            "주요 이슈의 상위 카테고리명. "
            "운영진이 사전에 정의한 category_template 중 하나여야 하며, "
            "동일 주차에서 가장 중요한 이슈 Top3 중 하나를 의미한다."
        ),
    )

    count: int = Field(
        ...,
        description=(
            "해당 카테고리에 속한 활성(active) 로그의 개수. "
            "중복 제거(dedup) 및 split 처리 이후의 최종 집계 수치를 사용한다."
        ),
    )

    summary: str = Field(
        ...,
        description=(
            "해당 카테고리의 핵심 이슈를 1~2문장으로 요약한 설명. "
            "운영진이 바로 상황을 이해하고 판단할 수 있도록 "
            "원인과 문제의 성격이 드러나게 작성한다."
        ),
    )

    post_ids: List[str] = Field(
        default_factory=list,
        description=(
            "이 KeyTopic을 구성하는 대표 로그들의 post_id 목록. "
            "전체 로그가 아니라, 의미를 가장 잘 대표하는 일부(post 대표본)만 포함한다."
        ),
    )

    texts: List[str] = Field(
        default_factory=list,
        description=(
            "ai_analysis.clean_text 기반의 대표 excerpt 목록. "
            "운영진이 실제 사용자 표현을 빠르게 확인할 수 있도록 사용되며, "
            "각 항목은 1문장 또는 120자 이내의 짧은 텍스트여야 한다."
        ),
    )


class OpsAction(BaseModel):
    title: str = Field(
        ...,
        description=(
            "운영 개입 가이드의 한 줄 제목. "
            "무엇을 해야 하는지 바로 이해할 수 있도록 행동 중심으로 작성한다."
        ),
    )

    target: str = Field(
        ...,
        description=(
            "해당 운영 액션의 대상. "
            "예: 'AI 1반 전체', '팀장', '운영진', '직장 병행 수강생' 등"
        ),
    )

    reason: str = Field(
        ...,
        description=(
            "이 액션이 필요한 근거 설명. "
            "어떤 로그 패턴/이슈/위험도가 관찰되었는지를 요약해 작성한다."
        ),
    )

    todo: str = Field(
        ...,
        description=(
            "운영진이 실제로 실행해야 할 구체적인 행동 지침. "
            "추상적인 방향 제시가 아니라, "
            "'언제/무엇을/어떻게' 할지 드러나게 작성한다."
        ),
    )

    action_type: Literal["immediate", "short", "long"] = Field(
        ...,
        description=(
            "운영 개입의 시급도 분류.\n"
            "- immediate: 즉각 조치 필요 (갈등 확산, 위험 신호)\n"
            "- short: 단기 대응 가능 (1~2주 내 개선 가능)\n"
            "- long: 구조적/중장기 개선 과제"
        ),
    )


class WeeklyReport(BaseModel):
    week_summary: str = Field(
        ...,
        description=(
            "이번 주 속닥숲 전반의 상태를 요약한 문단. "
            "2~4문장 분량으로, "
            "주요 이슈 경향, 위험 신호, 운영 관점에서의 핵심 포인트를 포함한다."
        ),
    )

    key_topics: List[KeyTopic] = Field(
        default_factory=list,
        description=(
            "이번 주 주요 이슈 Top 3 목록. "
            "'요청 수 + 운영 중요도 + 위험도 가중치'를 종합하여 선정한다."
        ),
        min_items=3,
        max_items=3,
    )

    ops_actions: List[OpsAction] = Field(
        default_factory=list,
        description=(
            "주요 이슈에 대응하기 위한 운영 개입 가이드 목록. "
            "보통 Top 3 수준으로 생성되며, "
            "각 액션은 서로 다른 action_type을 가질 수 있다."
        ),
        min_items=3,
        max_items=3,
    )


class FinalizePayload(BaseModel):
    logs: List[Dict[str, Any]] = Field(
        ...,
        description=(
            "프론트엔드에 전달되는 최종 로그 데이터. "
            "FeedbackBoardPost + ai_analysis 정보를 rows 형태로 변환한 결과이며, "
            "리포트 화면에서 글 목록/드릴다운에 사용된다."
        ),
    )

    week_summary: str = Field(
        ...,
        description="WeeklyReport.week_summary와 동일한 주간 요약 문구.",
    )

    key_topics: List[KeyTopic] = Field(
        ...,
        description="WeeklyReport.key_topics를 그대로 프론트로 전달한 데이터.",
    )

    ops_actions: List[OpsAction] = Field(
        ...,
        description="WeeklyReport.ops_actions를 그대로 프론트로 전달한 데이터.",
    )

    stats: Dict[str, Any] = Field(
        ...,
        description=(
            "위험/주의/보통 분포, 부정글 비율, 카테고리별 집계 등 "
            "프론트 대시보드에서 사용하는 모든 수치 지표 모음."
        ),
    )

    wordcloud_keywords: List[str] = Field(
        default_factory=list,
        description=(
            "워드클라우드 생성을 위한 키워드 리스트. "
            "중복 제거 및 중요도 기반 필터링이 완료된 상태의 키워드만 포함한다."
        ),
    )


# ----------------------------
# 4) Agent State for LangGraph
# ----------------------------

class FeedbackBoardState(BaseModel):
    # input
    input: PipelineInput

    # raw + working
    raw_posts: List[FeedbackBoardPost] = Field(default_factory=list)
    posts: List[FeedbackBoardPost] = Field(default_factory=list)  # split 포함, 계속 여기로 진행

    # derived
    weekly_context: Optional[WeeklyContext] = None
    weekly_report: Optional[WeeklyReport] = None
    final: Optional[FinalizePayload] = None

    # debug / tracing
    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
