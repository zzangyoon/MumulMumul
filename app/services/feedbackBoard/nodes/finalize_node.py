# app/services/feedbackBoard/nodes/finalize_node.py
import sys
from pathlib import Path

# 이 파일 기준으로 프로젝트 루트 계산
CURRENT_FILE = Path(__file__).resolve()
ROOT_DIR = CURRENT_FILE.parents[4]   # .../MumulMumul
sys.path.append(str(ROOT_DIR))

from datetime import datetime
from typing import Any, Dict, List, Optional

from app.config import WEEK_INDEX
from app.services.db_service.camp import get_camp_by_id
from app.services.feedbackBoard.io_contract import FeedbackBoardState, FinalizePayload
from app.services.feedbackBoard.schemas import (
    FeedbackWeeklyReport,
    WeeklyKeyTopic,
    WeeklyOpsAction,
    WeeklyStats,
    WeeklyWordcloud,
    WeeklyContextSnapshot,
)
from app.services.db_service.feedback_reports import upsert_weekly_report
from app.services.feedbackBoard.schemas import FeedbackBoardPost


def _post_to_row(post) -> FeedbackBoardPost:
    """
    프론트가 기대하는 rows 형태로 변환.
    - 원문(raw_text) 대신 clean_text 우선
    - ai_analysis 없는 경우도 안전하게 처리
    """
    a = post.ai_analysis
    text = (a.clean_text if (a and a.clean_text) else post.raw_text) if post.raw_text else ""

    return FeedbackBoardPost(
        post_id=post.post_id,
        camp_id=post.camp_id,
        author_id=post.author_id,
        raw_text=text,
        created_at=post.created_at,
        ai_analysis=post.ai_analysis,
    )


def _build_weekly_stats(state: FeedbackBoardState) -> WeeklyStats:
    """
    state.weekly_context.risk 기반으로 WeeklyStats 구성
    없으면 state.posts를 직접 집계하여 구성
    """
    wc = state.weekly_context
    posts = state.posts

    # wc.risk 가 없으면 에러
    if wc is None or wc.risk is None:
        raise ValueError("weekly_context.risk is required to build WeeklyStats")

    total = wc.risk.total
    toxic = wc.risk.toxic_count
    ratio = (toxic / total) if total else 0.0

    # active_posts는 "is_active True" 기준
    active_posts = sum(1 for p in posts if (p.ai_analysis is None or p.ai_analysis.is_active))

    # category/sub_category 집계는 weekly_context.categories로부터 만들기
    category_count: Dict[str, int] = {}
    sub_category_count: Dict[str, int] = {}
    for cat in (wc.categories or []):
        category_count[cat.category] = cat.count
        for sub in (cat.sub_items or []):
            sub_category_count[f"{cat.category}::{sub.sub_category}"] = sub.count

    return WeeklyStats(
        total_posts=total,
        active_posts=active_posts,
        toxic_posts=toxic,
        toxic_ratio=ratio,
        danger_count=wc.risk.danger_count,
        warning_count=wc.risk.warning_count,
        normal_count=wc.risk.normal_count,
        severity_count=wc.risk.severity_count,
        category_count=category_count,
        sub_category_count=sub_category_count,
        action_type_count=wc.action_type_count or {},
    )


def finalize_node(state: FeedbackBoardState) -> FeedbackBoardState:
    """
    - FinalizePayload 생성(프론트 응답용)
    - FeedbackWeeklyReport 생성(DB 저장용)
    - DB upsert 저장
    """
    cfg = state.input.config
    camp_id = cfg.camp_id
    week = cfg.week
    analyzer_version = cfg.analyzer_version

    if state.weekly_report is None:
        state.errors.append("weekly_report is None (weekly_report_node 결과가 필요)")
        return state

    # 1) logs 생성: ai_analysis 기준으로 필터링 후 rows 변환
    filtered_posts = []
    for post in state.posts:
        ai_analysis = post.ai_analysis
        if ai_analysis is None:
            filtered_posts.append(post)
            continue
        
        if ai_analysis.is_active and (ai_analysis.is_group_representative is None or ai_analysis.is_group_representative is True):
            filtered_posts.append(post)

    rows: List[Dict[str, Any]] = [_post_to_row(p) for p in filtered_posts]

    # 2) stats
    stats_model: WeeklyStats = _build_weekly_stats(state)

    # 워드클라우드 키워드 집계
    wc_keywords: List[str] = []
    
    # 워드클라우드 키워드 집계
    for post in filtered_posts:
        if post.ai_analysis and post.ai_analysis.keywords:
            # 하나의 포스트내에서 중복 제거
            wc_keywords.extend(list(set(post.ai_analysis.keywords)))

    # FinalizePayload 생성
    final = FinalizePayload(
        logs=rows,
        week_summary=state.weekly_report.week_summary,
        key_topics=[kt.model_dump() for kt in state.weekly_report.key_topics],
        ops_actions=[oa.model_dump() for oa in state.weekly_report.ops_actions],
        stats=stats_model.model_dump(),
        wordcloud_keywords=wc_keywords,
    )
    state.final = final

    # DB 저장용 FeedbackWeeklyReport 생성
    db_key_topics: List[WeeklyKeyTopic] = []
    for key_topic in state.weekly_report.key_topics:
        db_key_topics.append(
            WeeklyKeyTopic(
                category=key_topic.category,
                count=key_topic.count,
                summary=key_topic.summary,
                post_ids=[str(pid) for pid in (key_topic.post_ids or [])],
                excerpts=key_topic.texts[:5],
            )
        )

    db_ops_actions: List[WeeklyOpsAction] = []
    for ops_action in state.weekly_report.ops_actions:
        db_ops_actions.append(
            WeeklyOpsAction(
                title=ops_action.title,
                target=ops_action.target,
                reason=ops_action.reason,
                todo=ops_action.todo,
                action_type=ops_action.action_type,
            )
        )

    # context snapshot
    snapshot = None
    if state.weekly_context is not None:
        snapshot = WeeklyContextSnapshot(
            categories=[c.model_dump() for c in (state.weekly_context.categories or [])],
            highlights=[h.model_dump() for h in (state.weekly_context.highlights or [])],
        )

    # source_post_ids (대표/active만 저장 권장)
    source_post_ids = []
    for post in filtered_posts:
        source_post_ids.append(str(post.post_id))

    report = FeedbackWeeklyReport(
        # is_active 가 true인 글만
        logs = final.logs,
        camp_id=camp_id,
        week=week,
        analyzer_version=analyzer_version,
        generated_at=datetime.utcnow(),
        week_summary=state.weekly_report.week_summary,
        key_topics=db_key_topics,
        ops_actions=db_ops_actions,
        stats=stats_model,
        wordcloud=WeeklyWordcloud(keywords=wc_keywords),
        source_post_ids=source_post_ids,
        source_min_created_at=min((p.created_at for p in filtered_posts), default=None),
        source_max_created_at=max((p.created_at for p in filtered_posts), default=None),
        context_snapshot=snapshot,
    )

    # DB upsert 저장
    try:
        saved = upsert_weekly_report(report)
        # 필요하면 state.warnings에 저장 결과를 남겨도 됨
        state.warnings.append(f"weekly_report saved: camp={camp_id}, week={week}, ver={analyzer_version}")
    except Exception as e:
        state.errors.append(f"failed to save weekly_report: {e}")

    return state


if __name__ == "__main__":
    from datetime import datetime

    # 1) finalize_node가 있는 모듈에서 "upsert_weekly_report"를 스텁으로 교체
    #    (DB 없이도 finalize_node가 통과하도록)
    def _stub_upsert_weekly_report(report):
        # 최소한의 형태 검증만 하고 그대로 반환
        assert report.camp_id == 1
        assert report.week == 1
        assert report.analyzer_version == "fb_test"
        assert report.stats.total_posts >= 0
        return report

    # finalize_node.py 상단에서
    #   from app.services.db_service.feedback_reports import upsert_weekly_report
    # 를 import 했으므로, "현재 모듈 네임스페이스"의 upsert_weekly_report를 덮으면 됨
    globals()["upsert_weekly_report"] = _stub_upsert_weekly_report

    # 2) 최소 State 구성
    from app.services.feedbackBoard.io_contract import (
        FeedbackBoardState,
        PipelineInput,
        RunConfig,
        WeeklyContext,
        RiskAgg,
        CategoryAgg,
        ClusterItem,
        KeyTopic,
        OpsAction,
        WeeklyReport,
        DateRange,
        RiskHighlight,
    )
    from app.services.feedbackBoard.schemas import FeedbackBoardPost, FeedbackBoardInsight

    cfg = RunConfig(
        camp_id=1,
        week=1,
        analyzer_version="fb_test",
        category_template=["팀 갈등", "일정 압박", "과제 난이도", "운영/행정", "피로/번아웃"],
    )
    state = FeedbackBoardState(input=PipelineInput(config=cfg))

    # 3) posts 더미(대표/active만 프론트 rows로 나가도록 구성)
    state.posts = [
        FeedbackBoardPost(
            post_id="p1",
            camp_id=1,
            author_id=101,
            raw_text="팀 역할이 애매해서 제가 혼자 맡는 일이 많은 것 같아요.",
            created_at=datetime(2025, 11, 3, 20, 0),
            ai_analysis=FeedbackBoardInsight(
                clean_text="팀 역할이 불명확해 특정 인원에게 업무가 집중되는 것 같습니다.",
                is_active=True,
                is_group_representative=True,
                category="팀 갈등",
                sub_category="역할 분배 갈등",
                post_type="고민",
                is_toxic=False,
                severity="medium",
                summary="역할 분배 불균형에 대한 고민",
                keywords=["역할", "업무", "분배"],
                action_type="short",
                analyzed_at=datetime.utcnow(),
                analyzer_version="fb_test",
            ),
        ),
        FeedbackBoardPost(
            post_id="p2",
            camp_id=1,
            author_id=101,
            raw_text="(중복) 팀 역할이 애매해서...",
            created_at=datetime(2025, 11, 3, 21, 0),
            ai_analysis=FeedbackBoardInsight(
                clean_text="(중복) 팀 역할이 애매하다는 내용입니다.",
                is_active=True,
                duplicate_group_id="dup_1",
                is_group_representative=False,  # 대표 아님 → finalize_node에서 logs 제외됨
                inactive_reasons=[],
                category="팀 갈등",
                sub_category="역할 분배 갈등",
                post_type="고민",
                is_toxic=False,
                severity="medium",
                summary="(중복) 역할 분배 불균형",
                keywords=["역할"],
                action_type="short",
                analyzed_at=datetime.utcnow(),
                analyzer_version="fb_test",
            ),
        ),
        FeedbackBoardPost(
            post_id="p3",
            camp_id=1,
            author_id=102,
            raw_text="팀장님이 의견을 잘 안 듣고 자기 스타일대로만 정해서 답답합니다.",
            created_at=datetime(2025, 11, 6, 21, 0),
            ai_analysis=FeedbackBoardInsight(
                clean_text="팀장이 의견을 충분히 수렴하지 않고 결정을 내린다는 불만이 있습니다.",
                is_active=True,
                is_group_representative=True,
                category="팀 갈등",
                sub_category="팀장-팀원 의사소통 문제",
                post_type="고민",
                is_toxic=True,
                toxicity_score=0.91,
                severity="high",
                summary="팀장 의사결정 방식에 대한 강한 불만",
                keywords=["팀장", "의사소통", "결정"],
                action_type="immediate",
                analyzed_at=datetime.utcnow(),
                analyzer_version="fb_test",
            ),
        ),
        FeedbackBoardPost(
            post_id="p4",
            camp_id=1,
            author_id=103,
            raw_text="ㅋㅋㅋㅋ",
            created_at=datetime(2025, 11, 4, 10, 0),
            ai_analysis=FeedbackBoardInsight(
                clean_text="",
                is_active=False,
                inactive_reasons=["meaningless"],
                analyzer_version="fb_test",
            ),
        ),
    ]

    # 4) weekly_context 더미(집계값/하이라이트 포함)
    state.weekly_context = WeeklyContext(
        camp_id=1,
        week=1,
        range=DateRange(
            start=datetime(2025, 11, 3),
            end=datetime(2025, 11, 10),
        ),
        risk=RiskAgg(
            total=3,  # active+대표만 기준으로 집계했다고 가정(p1,p3 + 다른 하나가 있었다고 가정 가능하지만 여기선 3으로 둠)
            toxic_count=1,
            severity_count={"low": 0, "medium": 1, "high": 1},
            danger_count=1,
            warning_count=1,
            normal_count=1,
        ),
        categories=[
            CategoryAgg(
                category="팀 갈등",
                count=2,
                sub_items=[
                    ClusterItem(
                        local_cluster_id=0,
                        sub_category="역할 분배 갈등",
                        representative_summary="역할 분배가 불명확해 업무가 집중된다는 의견",
                        representative_keywords=["역할", "분배"],
                        count=1,
                    ),
                    ClusterItem(
                        local_cluster_id=1,
                        sub_category="팀장-팀원 의사소통 문제",
                        representative_summary="팀장이 의견을 수렴하지 않는다는 불만",
                        representative_keywords=["팀장", "의사소통"],
                        count=1,
                    ),
                ],
            )
        ],
        highlights=[
            RiskHighlight(
                post_id="p3",
                created_at=datetime(2025, 11, 6, 21, 0),
                author_id=102,
                category="팀 갈등",
                sub_category="팀장-팀원 의사소통 문제",
                severity="high",
                is_toxic=True,
                summary="팀장 의사결정 방식에 대한 강한 불만",
                excerpt="팀장이 의견을 충분히 수렴하지 않고 결정...",
            )
        ],
        action_type_count={"immediate": 1, "short": 1, "long": 0},
    )

    # 5) weekly_report 더미 (✅ 여기서 key_topics에 post_ids를 채워서 내려온다고 가정)
    state.weekly_report = WeeklyReport(
        week_summary="1주차에는 팀 갈등 이슈가 두드러졌고, 일부 토식/고위험 표현이 관찰되었습니다.",
        key_topics=[
            KeyTopic(
                category="팀 갈등",
                count=2,
                summary="역할 분배 불균형 및 팀장-팀원 의사소통 문제가 반복적으로 등장했습니다.",
                post_ids=["p1", "p3"],  # ✅ 채움
                texts=[
                    "팀 역할이 불명확해 특정 인원에게 업무가 집중되는 것 같습니다.",
                    "팀장이 의견을 충분히 수렴하지 않고 결정을 내린다는 불만이 있습니다.",
                ],
            )
        ],
        ops_actions=[
            OpsAction(
                title="1. 팀 커뮤니케이션 룰 정리",
                target="AI 1반 전체",
                reason="팀 갈등 관련 고민이 반복적으로 언급됨",
                todo="팀 내 의사결정/역할 분배 기준을 문서로 합의",
                action_type="short",
            )
        ],
    )

    # 6) 실행
    from app.services.feedbackBoard.nodes.finalize_node import finalize_node

    out = finalize_node(state)

    # 7) 검증(assert)
    assert out.final is not None, "final payload가 생성되어야 함"
    assert out.final.week_summary, "week_summary가 있어야 함"
    assert isinstance(out.final.logs, list) and len(out.final.logs) > 0, "logs가 있어야 함"

    # 대표 아닌 중복(p2), inactive(p4)는 logs에서 제외되는지 확인
    log_ids = [r.get("parent_post_id") for r in out.final.logs]  # parent_post_id는 없을 수 있음
    # 대신 user_id + created_at로 확인해도 되고, 여기선 개수로 간단 확인:
    # 기대: 대표/active(p1, p3)만 들어가면 2개
    assert len(out.final.logs) == 2, f"대표+active만 포함되어야 함. got={len(out.final.logs)}"

    # key_topics에 post_ids가 포함되는지 확인
    # kt0 = out.final.key_topics[0]
    # assert "post_ids" in kt0 and kt0.post_ids == ['p1', 'p3'], "key_topics.post_ids가 전달되어야 함"

    # wordcloud_keywords는 리스트만 전달(이미지 없음)
    assert isinstance(out.final.wordcloud_keywords, list), "wordcloud_keywords는 list여야 함"

    print(out.final)

    print("✅ finalize_node test passed")