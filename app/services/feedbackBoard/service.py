from datetime import datetime
from langchain_openai import OpenAIEmbeddings
from requests import Session

from app.services.db_service.camp import get_week_range_by_index
from app.services.db_service.feedbackBoard import get_feedback_posts_by_date_range
from app.services.feedbackBoard.graph import run_feedbackboard_pipeline
from app.services.feedbackBoard.io_contract import FinalizePayload
from app.services.feedbackBoard.schemas import FeedbackWeeklyReport, WeeklyWordcloud


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

    print(start_date, end_date, camp_id, week_index)
    print(rows)
    
    result: FinalizePayload = run_feedbackboard_pipeline(rows, 
                                                         camp_id=camp_id, 
                                                         week=week_index, 
                                                         category_template=["운영", "커리큘럼", "프로젝트", "공간", "기타"],
                                                         )

    return {
        "logs": result.logs,
        "week_summary_by_camp_week": result.week_summary,
        "key_topics_by_camp_week": result.key_topics,
        "ops_actions_by_camp_week": result.ops_actions,
    }
