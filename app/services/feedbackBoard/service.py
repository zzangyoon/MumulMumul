from requests import Session

from app.services.db_service.camp import get_week_range_by_index
from app.services.db_service.feedbackBoard import get_feedback_posts_by_date_range


def build_feedback_report(
    db: Session,
    camp_id: int,
    week_index: int,
) -> dict:
    """
    1) 기간 내 FeedbackBoardPost 로드
    2) 아직 분석 안 된 글이면 → 일괄 분석 (필터링/의미 분리/분류/위험도/요약/키워드)
    3) 주간 기준으로 aggregate 해서
       - logs
       - week_summary_by_camp_week
       - key_topics_by_camp_week
       - ops_actions_by_camp_week
       를 만들어서 반환
    """
    # 1) 기간 내 FeedbackBoardPost 로드
    start_date, end_date = get_week_range_by_index(
        db,
        camp_id,
        week_index,
    )

    rows = get_feedback_posts_by_date_range(camp_id, start_date, end_date)

    # 2) 아직 분석 안 된 글이면 → 일괄 분석 (필터링/분류/위험도/요약/키워드)
    for row in rows:
        if not row.is_analyzed:
            pass  # TODO: 분석 로직 추가
    
    # 3) 주간 기준으로 aggregate 해서 반환
    

    ...
    return {
        "logs": rows,
        "week_summary_by_camp_week": ...,
        "key_topics_by_camp_week": ...,
        "ops_actions_by_camp_week": ...,
    }
