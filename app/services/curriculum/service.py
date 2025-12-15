# app/services/curriculum/service.py
from sqlalchemy.orm import Session
from pymongo.database import Database

from app.core.mongodb import CurriculumConfig, CurriculumInsights, CurriculumReport
from app.services.curriculum.generate_log_insights.llm import insights_chain
from app.services.curriculum.generate_log_insights.prompts import CurriculumInsightsBatch
from app.services.db_service.camp import get_camp_by_id
from app.services.db_service.curriculum_config import get_curriculum_config_for_camp
from app.services.db_service.curriculum_reports import fetch_curriculum_report, upsert_curriculum_report
from app.services.db_service.learning_chat_log import get_week_range_by_index, update_insights_for_logs, fetch_weekly_logs_no_insights, fetch_weekly_logs

from .agent import generate_curriculum_report


from datetime import datetime
from typing import Any, Dict, List, Optional


def generate_curriculum_insights_with_llm(
    logs: List[Dict[str, Any]],
    curriculum_config: Optional[CurriculumConfig],
) -> List[CurriculumInsights]:
    """
    Mongo에 저장할 curriculum_insights 생성용 헬퍼.
    반환값은 ai_insights_parser 의 pydantic 모델(List[...] 등) 그대로.
    """
    result: CurriculumInsightsBatch = insights_chain.invoke(
        {
            "logs": logs,
            "curriculum_config": curriculum_config,
        }
    )
    return result.items

def get_curriculum_report(camp_id: int, camp_name: str, week_index: int, week_start, week_end) -> CurriculumReport | None:
    existing = fetch_curriculum_report(camp_id, week_index)
    if existing:
        # Mongo _id 제거 후 Pydantic 모델로 변환
        existing.pop("_id", None)
        print(f"리포트 조회 camp_id={camp_id}, week_index={week_index}.")
        return CurriculumReport(
            camp_name=camp_name,
            week_label=f"Week {week_index}",
            week_start=week_start,
            week_end=week_end,
            **existing,  # core 안에 summary_cards, charts, tables, ai_insights, raw_stats 등이 있어야 함
        )
    return None

def create_curriculum_report(
    db: Session,
    mongo_db: Database,
    camp_id: int,
    week_index: int,
) -> CurriculumReport:
    """
    캠프 ID와 주차 인덱스를 받아서 커리큘럼 리포트를 생성/조회.
    """

    camp = get_camp_by_id(db, camp_id)
    week_start, week_end = get_week_range_by_index(db, camp_id, week_index)

    # 1) 기존 리포트 조회
    # report = get_curriculum_report(camp_id, camp.name, week_index, week_start, week_end)
    # if report:
    #     return report
    
    # # 2) 리포트가 없으면 새로 생성
    # print(f"리포트 조회 실패 camp_id={camp_id}, week_index={week_index}. 새로운 리포트 생성 시작.")

    # 2-2) 해당 주차 로그에 대해 CurriculumInsights 없으면 생성
    weekly_logs_no_insights = fetch_weekly_logs_no_insights(db, camp_id=camp_id, week_index=week_index)
    if len(weekly_logs_no_insights) > 0:
        curriculum_config = get_curriculum_config_for_camp(camp_id=camp_id)
        curriculum_insights: List[CurriculumInsights] = generate_curriculum_insights_with_llm(
            logs=weekly_logs_no_insights,
            curriculum_config=curriculum_config)

        for insight in curriculum_insights:
            print(f"- Id: {insight.id} - Topics: {insight.topic} - Scope: {insight.scope} - Intent: {insight.intent} - Tags: {insight.pattern_tags}")
        
        update_insights_for_logs(curriculum_insights)

    # 2-3) 주차 로그 조회 (이미 insights가 붙어 있다고 가정)
    print(f"주차 로그 조회 시작 camp_id={camp_id}, week_index={week_index}.")
    weekly_logs = fetch_weekly_logs(db, camp_id=camp_id, week_index=week_index)

    # 2-4) 리포트 생성
    print(f"리포트 생성 시작 camp_id={camp_id}, week_index={week_index}.")
    report: CurriculumReport = generate_curriculum_report(
        camp_id=camp_id,
        weekly_logs=weekly_logs,
    )

    # 3) 리포트 MongoDB에 저장
    print(f"리포트 저장 시작 camp_id={camp_id}, week_index={week_index}.")
    now = datetime.utcnow()
    report["created_at"] = now

    upsert_curriculum_report(camp_id=camp_id, week_index=week_index, report_data=report)

    return CurriculumReport(
        camp_id=camp_id,
        camp_name=camp.name,
        week_index=week_index,
        week_label=f"Week {week_index}",
        week_start=week_start,
        week_end=week_end,
        **report,
    )

