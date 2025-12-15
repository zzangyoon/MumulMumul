# app/services/feedbackBoard/utils_weekly_context.py
import sys
from pathlib import Path

# 이 파일 기준으로 프로젝트 루트 계산
CURRENT_FILE = Path(__file__).resolve()
ROOT_DIR = CURRENT_FILE.parents[4]   # .../MumulMumul
sys.path.append(str(ROOT_DIR))

from typing import Dict, Any, List, Optional, Literal
from collections import Counter

from app.services.feedbackBoard.io_contract import WeeklyContext


def build_weekly_report_llm_context(
    weekly_context: WeeklyContext,
    *,
    max_categories: int = 5,
    max_subitems_per_category: int = 6,
    max_highlights: int = 6,
    keywords_per_cluster: int = 8,
) -> Dict[str, Any]:
    """
    weekly_report_node에 넣을 'LLM용 압축 컨텍스트'를 만든다.

    목표:
    - posts 전체를 넣지 않는다 (context 폭발 방지)
    - 운영진 판단에 필요한 신호만 요약해서 제공
    - 카테고리/서브카테고리 단위의 action_type(immediate/short/long)을 같이 전달

    전제:
    - action_classify_node에서 ClusterItem.action_type이 채워져 있어야 최적 품질.
    """

    risk = weekly_context.risk

    # 1) 카테고리 정렬: count 내림차순 + 최대 N개
    categories_sorted = sorted(
        weekly_context.categories,
        key=lambda c: c.count,
        reverse=True,
    )[:max_categories]

    compact_categories: List[Dict[str, Any]] = []
    action_type_counter = Counter()

    for cat in categories_sorted:
        # sub_items 정렬: count 내림차순 + 최대 M개
        sub_sorted = sorted(
            cat.sub_items,
            key=lambda s: s.count,
            reverse=True,
        )[:max_subitems_per_category]

        compact_subs: List[Dict[str, Any]] = []
        for s in sub_sorted:
            # (핵심) 안건 단위 action_type
            action_type = getattr(s, "action_type", None)  # Optional[str]
            if action_type in ("immediate", "short", "long"):
                action_type_counter[action_type] += 1
            else:
                action_type = None

            compact_subs.append(
                {
                    "local_cluster_id": s.local_cluster_id,
                    "sub_category": s.sub_category,
                    "count": s.count,
                    "representative_summary": s.representative_summary,
                    "representative_keywords": (s.representative_keywords or [])[:keywords_per_cluster],
                    "action_type": action_type,  # immediate | short | long | None
                }
            )

        compact_categories.append(
            {
                "category": cat.category,
                "count": cat.count,
                "sub_items": compact_subs,
            }
        )

    # 2) 하이라이트 정렬: high 우선, toxic 우선, 최신 우선
    def _sev_rank(x: Optional[str]) -> int:
        if x == "high":
            return 0
        if x == "medium":
            return 1
        return 2

    highlights_sorted = sorted(
        weekly_context.highlights,
        key=lambda h: (
            _sev_rank(h.severity),
            0 if (h.is_toxic is True) else 1,
            -int(h.created_at.timestamp()),
        ),
    )[:max_highlights]

    compact_highlights: List[Dict[str, Any]] = []
    for h in highlights_sorted:
        compact_highlights.append(
            {
                "post_id": h.post_id,
                "created_at": h.created_at.isoformat(),
                "author_id": h.author_id,
                "category": h.category,
                "sub_category": h.sub_category,
                "severity": h.severity,
                "is_toxic": h.is_toxic,
                "summary": h.summary,
                "excerpt": h.excerpt,
            }
        )

    # 3) action_type_count
    # - aggregate_weekly_context_node에서 이미 계산해줬다면 그 값을 사용
    # - 없으면 sub_items 기반으로 추정
    action_type_count = dict(weekly_context.action_type_count or {})
    if not action_type_count:
        action_type_count = {
            "immediate": int(action_type_counter.get("immediate", 0)),
            "short": int(action_type_counter.get("short", 0)),
            "long": int(action_type_counter.get("long", 0)),
        }

    # 4) 최종 LLM 입력 컨텍스트
    return {
        "meta": {
            "camp_id": weekly_context.camp_id,
            "week": weekly_context.week,
            "range": {
                "start": weekly_context.range.start.isoformat(),
                "end": weekly_context.range.end.isoformat(),
            }
            if weekly_context.range
            else None,
        },
        "risk": {
            "total": risk.total,
            "toxic_count": risk.toxic_count,
            "severity_count": risk.severity_count,
            "danger_count": risk.danger_count,
            "warning_count": risk.warning_count,
            "normal_count": risk.normal_count,
        },
        "categories": compact_categories,
        "highlights": compact_highlights,
        "action_type_count": action_type_count,
        "scoring_hint": {
            "key_topics_should_consider": [
                "요청 수(=count)",
                "운영 중요도(=category template 기준 가중)",
                "위험도(=toxic/severity/highlights)",
            ],
            "ops_actions_should_cover": ["immediate", "short", "long"],
        },
    }


# =========================================================
# 하단 테스트 코드 (요구사항 반영)
# =========================================================
if __name__ == "__main__":
    from datetime import datetime
    import json

    # io_contract를 그대로 쓰는 전제 (네 프로젝트에 이미 존재)
    from app.services.feedbackBoard.io_contract import (
        WeeklyContext,
        DateRange,
        RiskAgg,
        CategoryAgg,
        ClusterItem,
        RiskHighlight,
    )

    wc = WeeklyContext(
        camp_id=1,
        week=1,
        range=DateRange(
            start=datetime(2025, 11, 3),
            end=datetime(2025, 11, 10),
        ),
        risk=RiskAgg(
            total=10,
            toxic_count=2,
            severity_count={"low": 4, "medium": 4, "high": 2},
            danger_count=3,
            warning_count=4,
            normal_count=3,
        ),
        categories=[
            CategoryAgg(
                category="팀 갈등",
                count=5,
                sub_items=[
                    ClusterItem(
                        local_cluster_id=0,
                        sub_category="팀장-팀원 의사소통 문제",
                        representative_summary="팀장이 의견을 잘 반영하지 않아 답답하다는 불만이 반복됨.",
                        representative_keywords=["의사소통", "팀장", "결정", "답답"],
                        count=3,
                    ),
                    ClusterItem(
                        local_cluster_id=1,
                        sub_category="역할 분배 갈등",
                        representative_summary="업무가 한 사람에게 몰리는 느낌이라는 문제 제기.",
                        representative_keywords=["역할", "분배", "업무량"],
                        count=2,
                    ),
                ],
            ),
            CategoryAgg(
                category="일정 압박",
                count=3,
                sub_items=[
                    ClusterItem(
                        local_cluster_id=2,
                        sub_category="데드라인 부담",
                        representative_summary="평일 저녁 마감이 직장 병행자에게 과도하게 촉박함.",
                        representative_keywords=["마감", "평일", "촉박"],
                        count=3,
                    )
                ],
            ),
        ],
        highlights=[
            RiskHighlight(
                post_id="p1",
                created_at=datetime(2025, 11, 6, 21, 0),
                author_id=101,
                category="팀 갈등",
                sub_category="팀장-팀원 의사소통 문제",
                severity="high",
                is_toxic=True,
                summary="팀장의 일방적 결정에 대한 강한 불만이 표출됨.",
                excerpt="팀장님이 의견을 잘 안 듣고 자기 스타일대로만 정해서 답답합니다.",
            )
        ],
        action_type_count={},  # 없으면 아래 action_type 기반으로 추정
    )

    # 테스트: action_classify_node 결과가 들어왔다고 가정
    # (ClusterItem에 action_type 필드가 있어야 함)
    wc.categories[0].sub_items[0].action_type = "immediate"
    wc.categories[0].sub_items[1].action_type = "short"
    wc.categories[1].sub_items[0].action_type = "short"

    ctx = build_weekly_report_llm_context(wc)

    print("===== weekly_report_node LLM context =====")
    print(json.dumps(ctx, ensure_ascii=False, indent=2))

    # 간단 검증
    assert ctx["risk"]["total"] == 10
    assert "categories" in ctx and len(ctx["categories"]) > 0
    assert "action_type_count" in ctx
    assert ctx["action_type_count"]["immediate"] >= 1
    print("✅ TEST PASSED")
