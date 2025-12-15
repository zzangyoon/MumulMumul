# app/services/feedbackBoard/nodes/weekly_report_node.py
import sys
from pathlib import Path

# 이 파일 기준으로 프로젝트 루트 계산
CURRENT_FILE = Path(__file__).resolve()
ROOT_DIR = CURRENT_FILE.parents[4]   # .../MumulMumul
sys.path.append(str(ROOT_DIR))

import json
from typing import List

from pydantic import BaseModel, Field

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser

# 실제 프로젝트 경로에 맞춰 import 조정
from app.services.feedbackBoard.io_contract import (
    FeedbackBoardState,
    WeeklyReport,
    KeyTopic,
    OpsAction,
)


# -----------------------------
# LLM 전용 초소형 출력 모델
# -----------------------------
class WeeklyReportLLMOut(BaseModel):
    week_summary: str = Field(
        ...,
        description=(
            "이번 주 전체 분위기/핵심 흐름을 운영진이 빠르게 이해할 수 있게 2~4문장으로 요약. "
            "숫자/정답 데이터(건수/분류)는 입력에 있는 것을 참고만 하고, 과장하지 말 것."
        ),
    )
    key_topic_summaries: List[str] = Field(
        default_factory=list,
        description=(
            "Top3 key topic 후보 각각에 대한 요약 문장 리스트. "
            "입력의 후보 순서와 동일한 순서로 작성. 각 항목 2~3문장."
        ),
    )
    ops_action_todos: List[str] = Field(
        default_factory=list,
        description=(
            "운영 개입 가이드 후보 각각에 대한 실행 To-do 문장 리스트. "
            "입력 후보 순서와 동일한 순서로 작성. 각 항목은 구체적 행동 중심으로 2~4문장."
        ),
    )


def weekly_report_node(state: FeedbackBoardState, llm) -> FeedbackBoardState:
    """
    - 입력: state.weekly_context (이미 Top3 후보/ops 후보 계산 완료 상태)
    - 처리: LLM 1회 호출로 week_summary + (Top3 summary 문장) + (ops todo 문장)만 생성
    - 출력: state.weekly_report (정답 데이터는 후보에서 복사하여 서버가 조립)
    """
    weekly_context = state.weekly_context
    if weekly_context is None:
        state.errors.append("weekly_report_node: weekly_context is None")
        return state

    # 후보가 없으면 LLM 호출 자체를 스킵하고 최소 리포트 생성
    key_cands = weekly_context.key_topic_candidates or []
    ops_cands = weekly_context.ops_action_candidates or []

    parser = PydanticOutputParser(pydantic_object=WeeklyReportLLMOut)
    format_instructions = parser.get_format_instructions()

    key_cands_payload = [
        {
            "category": c.category,
            "sub_category": c.sub_category,
            "count": c.count,
            "representative_summary": c.representative_summary,
            "representative_keywords": c.representative_keywords,
            "excerpts": c.excerpts,
            "score": c.score,
        }
        for c in key_cands
    ]

    ops_cands_payload = [
        {
            "title": a.title,
            "target": a.target,
            "reason": a.reason,
            "action_type": a.action_type,
            "related_excerpts": a.related_excerpts,
        }
        for a in ops_cands
    ]

    # risk 요약도 "숫자만" 전달
    risk_payload = {
        "total": weekly_context.risk.total,
        "toxic_count": weekly_context.risk.toxic_count,
        "severity_count": weekly_context.risk.severity_count,
        "danger_count": weekly_context.risk.danger_count,
        "warning_count": weekly_context.risk.warning_count,
        "normal_count": weekly_context.risk.normal_count,
        "action_type_count": weekly_context.action_type_count,
    }

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                (
                    "너는 부트캠프 운영진을 위한 '익명 게시판(속닥숲) 주간 리포트' 작성 AI다.\n"
                    "- 반드시 입력에 있는 후보/수치만 참고한다.\n"
                    "- 절대 새로운 사실/숫자/분류를 만들어내지 않는다.\n"
                    "- 문장만 자연스럽게 작성한다(정리/표현/구체화).\n"
                    "- 출력은 JSON 하나만. 추가 텍스트 금지.\n\n"
                    "{format_instructions}"
                ),
            ),
            (
                "human",
                (
                    "다음은 이번 주 집계된 컨텍스트다.\n\n"
                    "1) 위험/지표 요약(risk):\n{risk_json}\n\n"
                    "2) Top3 후보(key_topic_candidates) - 이미 선정된 순서 그대로 요약 문장만 작성:\n{key_candidates_json}\n\n"
                    "3) 운영 액션 후보(ops_action_candidates) - action_type은 이미 결정됨. todo 문장만 구체화:\n{ops_candidates_json}\n\n"
                    "요구사항:\n"
                    "- week_summary: 2~4문장\n"
                    "- key_topic_summaries: 후보 개수만큼(순서 유지)\n"
                    "- ops_action_todos: 후보 개수만큼(순서 유지)\n"
                ),
            ),
        ]
    )

    chain = prompt | llm | parser

    try:
        llm_out: WeeklyReportLLMOut = chain.invoke(
            {
                "format_instructions": format_instructions,
                "risk_json": json.dumps(risk_payload, ensure_ascii=False),
                "key_candidates_json": json.dumps(key_cands_payload, ensure_ascii=False),
                "ops_candidates_json": json.dumps(ops_cands_payload, ensure_ascii=False),
            }
        )
    except Exception as e:
        state.errors.append(f"weekly_report_node: LLM parse/invoke failed: {e}")
        return state

    # -----------------------------
    # 서버가 WeeklyReport 조립
    # -----------------------------
    kt_summ = llm_out.key_topic_summaries or []
    oa_todos = llm_out.ops_action_todos or []

    if len(kt_summ) != len(key_cands):
        state.warnings.append(
            f"weekly_report_node: key_topic_summaries length mismatch "
            f"(expected={len(key_cands)}, got={len(kt_summ)}). Will pad/truncate."
        )
    if len(oa_todos) != len(ops_cands):
        state.warnings.append(
            f"weekly_report_node: ops_action_todos length mismatch "
            f"(expected={len(ops_cands)}, got={len(oa_todos)}). Will pad/truncate."
        )

    # pad/truncate
    def _fit(lst: List[str], n: int) -> List[str]:
        lst = lst[:n]
        while len(lst) < n:
            lst.append("")  # 비어있으면 빈 문장
        return lst

    kt_summ = _fit(kt_summ, len(key_cands))
    oa_todos = _fit(oa_todos, len(ops_cands))

    key_topics: List[KeyTopic] = []
    for i, key_topic in enumerate(key_cands):
        key_topics.append(
            KeyTopic(
                category=key_topic.category,
                count=key_topic.count,
                summary=kt_summ[i],
                post_ids=key_topic.post_ids,
                texts=key_topic.excerpts or [],
            )
        )

    ops_actions: List[OpsAction] = []
    for i, ops_action in enumerate(ops_cands):
        ops_actions.append(
            OpsAction(
                title=ops_action.title,
                target=ops_action.target,
                reason=ops_action.reason,
                todo=oa_todos[i],
                action_type=ops_action.action_type,
            )
        )

    state.weekly_report = WeeklyReport(
        week_summary=llm_out.week_summary,
        key_topics=key_topics,
        ops_actions=ops_actions,
    )
    return state


if __name__ == "__main__":
    # 1) 더미 state/weekly_context 준비 (프로젝트 io_contract 기준)
    from datetime import datetime
    from app.services.feedbackBoard.io_contract import (
        PipelineInput,
        RunConfig,
        DateRange,
        WeeklyContext,
        RiskAgg,
        CategoryAgg,
        ClusterItem,
        RiskHighlight,
        KeyTopicCandidate,
        OpsActionCandidate,
    )
    from app.services.feedbackBoard.schemas import FeedbackBoardPost, FeedbackBoardInsight

    # 2) Fake LLM (테스트 목적: 체인 흐름 + 파서만 확인)
    #    - LangChain Runnable처럼 invoke(input)->str 를 흉내내기 위해 최소 구현
    class FakeLLM:
        def __or__(self, other):
            # prompt | llm | parser 에서 llm이 가운데 들어가야 해서 단순 pass-through
            return self

        def invoke(self, _):
            # parser가 받는 건 '텍스트'이므로 JSON 문자열을 반환
            return json.dumps(
                {
                    "week_summary": "이번 주는 팀 내 의사소통/역할 분배 이슈가 두드러졌고, 일정 압박과 피로 호소가 함께 관찰되었습니다. 공지 채널 분산 문제도 개선 요구가 있습니다.",
                    "key_topic_summaries": [
                        "팀 역할 분배의 불균형과 팀장의 일방적 결정에 대한 불만이 반복되었습니다. 초기 팀 룰과 커뮤니케이션 합의가 필요합니다.",
                        "평일 저녁 마감이 직장 병행 수강생에게 지속적인 압박으로 작용하고 있습니다. 마감 완충 또는 과제량 조절 논의가 필요합니다.",
                        "공지 채널이 분산되어 중요한 안내를 놓치기 쉽다는 피드백이 있습니다. 공지 원칙과 게시 위치를 단일화하는 조치가 요구됩니다.",
                    ],
                    "ops_action_todos": [
                        "각 팀의 역할 분배 표를 간단히 정리해 공유하고, 업무량 편차가 큰 팀은 10분 조정 미팅을 진행하세요. 이후 익명 설문으로 역할 만족도를 확인하고 필요 시 운영진이 중재하세요.",
                        "과제 마감 시간을 12~24시간 완충하는 옵션을 공지로 안내하고, 직장 병행 수강생을 위한 시간관리 팁을 별도 제공하세요. 다음 주 과제 난이도 체감도 설문으로 조정 근거를 확보하세요.",
                        "중요 공지는 노션(단일)로만 게시하고 디스코드는 알림/링크 공유용으로 제한하는 원칙을 공지하세요. 공지 템플릿을 만들어 누락을 줄이세요.",
                    ],
                },
                ensure_ascii=False,
            )

    # 3) state 만들기
    state = FeedbackBoardState(
        input=PipelineInput(config=RunConfig(camp_id=1, week=1, range=DateRange(start=datetime(2025, 11, 3), end=datetime(2025, 11, 9)))),
        raw_posts=[],
        posts=[],
        weekly_context=None,
        weekly_report=None,
        final=None,
        warnings=[],
        errors=[],
    )

    # 4) weekly_context 더미 구성
    wc = WeeklyContext(
        camp_id=1,
        week=1,
        range=DateRange(start=datetime(2025, 11, 3), end=datetime(2025, 11, 9)),
        risk=RiskAgg(
            total=6,
            toxic_count=1,
            severity_count={"low": 2, "medium": 3, "high": 1},
            danger_count=1,
            warning_count=3,
            normal_count=2,
        ),
        categories=[
            CategoryAgg(
                category="팀 갈등",
                count=2,
                sub_items=[
                    ClusterItem(
                        local_cluster_id=0,
                        sub_category="역할 분배 갈등",
                        representative_summary="팀 역할이 공정하지 않다는 불만",
                        representative_keywords=["역할", "불균형", "업무량"],
                        count=1,
                        action_type="immediate",
                        post_ids=["p1"],
                    ),
                    ClusterItem(
                        local_cluster_id=1,
                        sub_category="팀장-팀원 의사소통 문제",
                        representative_summary="팀장이 의견을 잘 안 듣는다는 불만",
                        representative_keywords=["의사소통", "팀장", "답답"],
                        count=1,
                        action_type="immediate",
                        post_ids=["p6"],
                    ),
                ],
            )
        ],
        highlights=[
            RiskHighlight(
                post_id="p6",
                created_at=datetime(2025, 11, 6, 21, 0),
                author_id=101,
                category="팀 갈등",
                sub_category="팀장-팀원 의사소통 문제",
                severity="high",
                is_toxic=True,
                summary="팀장의 일방적 의사결정에 대한 강한 불만",
                excerpt="팀장님이 의견을 잘 안 듣고 자기 스타일대로만 정해서 답답합니다.",
            )
        ],
        action_type_count={"immediate": 2, "short": 1, "long": 0},
        key_topic_candidates=[
            KeyTopicCandidate(
                category="팀 갈등",
                sub_category="팀장-팀원 의사소통 문제",
                count=1,
                representative_summary="팀장이 의견을 잘 안 듣는다는 불만",
                representative_keywords=["의사소통", "팀장"],
                post_ids=["p6"],
                excerpts=["팀장님이 의견을 잘 안 듣고 자기 스타일대로만 정해서 답답합니다."],
                score=6.0,
            ),
            KeyTopicCandidate(
                category="일정 압박",
                sub_category="데드라인 부담",
                count=1,
                representative_summary="평일 저녁 마감이 촉박함",
                representative_keywords=["마감", "촉박", "회사"],
                post_ids=["p4"],
                excerpts=["평일 저녁 마감이라 회사 끝나고 과제를 하려니 촉박해요."],
                score=4.0,
            ),
            KeyTopicCandidate(
                category="운영/행정",
                sub_category="공지/소통 부족",
                count=1,
                representative_summary="공지 채널 분산으로 혼란",
                representative_keywords=["공지", "노션", "디스코드"],
                post_ids=["p3"],
                excerpts=["공지가 디스코드랑 노션에 나뉘어서 한 번에 보기 어려워요."],
                score=3.5,
            ),
        ],
        ops_action_candidates=[
            OpsActionCandidate(
                title="1. 팀 역할/소통 룰 정비",
                target="AI 1반 전체 + 각 팀 팀장",
                reason="팀 갈등 관련 이슈가 즉시 조치 필요(immediate)로 분류되었고, 고위험 하이라이트가 존재함.",
                action_type="immediate",
                related_post_ids=["p6", "p1"],
                related_excerpts=["팀장님이 의견을 잘 안 듣고... 답답합니다.", "팀 역할이 애매해서..."],
            ),
            OpsActionCandidate(
                title="2. 과제 마감 완충 및 적응 지원",
                target="AI 1반 전체 (특히 직장 병행 수강생)",
                reason="일정 압박이 단기 조정(short)으로 분류되었고 반복 가능성이 있음.",
                action_type="short",
                related_post_ids=["p4"],
                related_excerpts=["평일 저녁 마감이라... 촉박해요."],
            ),
            OpsActionCandidate(
                title="3. 공지 채널 일원화",
                target="AI 1반 전체",
                reason="운영/행정 이슈가 단기 조정(short)으로 분류되며 안내 체계 개선이 필요함.",
                action_type="short",
                related_post_ids=["p3"],
                related_excerpts=["공지가 디스코드랑 노션에..."],
            ),
        ],
    )

    state.weekly_context = wc

    # 5) 실행
    # NOTE: 실제 환경에서는 ChatOpenAI 같은 LLM을 넘기면 됨.
    # 여기서는 FakeLLM + Pydantic parser 흐름만 확인.
    from langchain_core.runnables import RunnableLambda

    # prompt | llm | parser 구조에서 llm이 Runnable이어야 해서
    # FakeLLM을 RunnableLambda로 감싸서 동일하게 동작시키는 방식
    fake_llm_runnable = RunnableLambda(lambda _: FakeLLM().invoke({}))

    state = weekly_report_node(state, llm=fake_llm_runnable)

    # 6) 결과 확인
    print("errors:", state.errors)
    print("warnings:", state.warnings)
    print("weekly_report:", state.weekly_report.model_dump() if state.weekly_report else None)
