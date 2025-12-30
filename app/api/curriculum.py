# app/api/curriculum.py
from datetime import datetime
from http.client import HTTPException
from typing import List, Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from pymongo.database import Database

from app.core.db import get_db
from app.core.mongodb import CurriculumReport, CurriculumWeek, CurriculumConfig, get_mongo_db
from app.core.schemas import Camp
from app.services.curriculum.analyze_curriculum.llm import parse_curriculum_text
from app.services.curriculum.service import create_curriculum_report, get_curriculum_report
from app.services.db_service.camp import get_camp_by_id
from app.services.db_service.curriculum_config import get_curriculum_config_for_camp, upsert_curriculum_config
from app.services.db_service.learning_chat_log import get_week_range_by_index

router = APIRouter()


@router.get("/camps")
def list_camps(db: Session = Depends(get_db)):
    """
    스트림릿 사이드바에서 '반 선택' 드롭다운용 캠프 목록 API
    """
    camps = db.query(Camp).all()
    return [
        {
            "camp_id": camp.camp_id,
            "name": camp.name,
        }
        for camp in camps
    ]

@router.get(
    "/newReport",
    response_model=CurriculumReport,
)
def create_curriculum_newReport(
    camp_id: int,
    week_index: int,  # "Week 1" / "Week 2" ...
    db: Session = Depends(get_db),
    mongo_db: Database = Depends(get_mongo_db),
) -> CurriculumReport:
    """
    특정 캠프 + 특정 주차의 커리큘럼 리포트 전체 Payload 반환 API
    (summary_cards, charts, tables, ai_insights 모두 포함)
    """
    payload = create_curriculum_report(
        db=db,
        mongo_db=mongo_db,
        camp_id=camp_id,
        week_index=week_index,
    )
    return payload

@router.get(
    "/report",
    response_model=Optional[CurriculumReport],
)
def fetch_curriculum_report(
    camp_id: int,
    week_index: int,  # "Week 1" / "Week 2" ...
    db: Session = Depends(get_db),
    mongo_db: Database = Depends(get_mongo_db),
) -> CurriculumReport | None:
    """
    특정 캠프 + 특정 주차의 커리큘럼 리포트 전체 Payload 반환 API
    (summary_cards, charts, tables, ai_insights 모두 포함)
    """
    camp = get_camp_by_id(db, camp_id)
    week_start, week_end = get_week_range_by_index(db, camp_id, week_index)

    # 1) 기존 리포트 조회
    report = get_curriculum_report(camp_id, camp.name, week_index, week_start, week_end)
    
    if not report:
        return None
    
    return report

mongo_db: Database = get_mongo_db()
curriculum_col = mongo_db["curriculum_configs"]

class CurriculumConfigIn(BaseModel):
    """
    클라이언트에서 입력받는 커리큘럼 설정.
    camp_id는 URL path에서 받고, 여기에는 주차 정보만 포함.
    """
    weeks: List[CurriculumWeek]


@router.get("/config/{camp_id}", response_model=CurriculumConfig)
def get_curriculum_config(camp_id: int) -> CurriculumConfig:
    doc = get_curriculum_config_for_camp(camp_id)
    if not doc:
        return CurriculumConfig(camp_id=camp_id, weeks=[])
        # raise HTTPException(status_code=404, detail="Curriculum config not found")

    return doc


@router.post("/config/{camp_id}", response_model=CurriculumConfig)
def update_curriculum_config(
    camp_id: int,
    payload: CurriculumConfigIn,
) -> CurriculumConfig:
    now = datetime.utcnow()

    update_doc = {
        "camp_id": camp_id,
        "weeks": [week.model_dump() for week in payload.weeks],
        "updated_at": now,
    }

    upsert_curriculum_config(
        camp_id=camp_id,
        update_doc=update_doc,
    )

    doc = get_curriculum_config_for_camp(camp_id)

    if not doc:
        raise HTTPException(status_code=500, detail="Failed to upsert curriculum config")

    return doc


class CurriculumParseRequest(BaseModel):
    raw_text: str

@router.post("/analyze/{camp_id}", response_model=CurriculumConfig)
def analyze_curriculum_text(
    camp_id: int,
    payload: CurriculumParseRequest,
) -> CurriculumConfig:
    
    config: CurriculumConfig = parse_curriculum_text(camp_id=camp_id, raw_text=payload.raw_text)

    now = datetime.utcnow()

    update_doc = {
            "camp_id": camp_id,
            "weeks": [week.model_dump() for week in config.weeks],
            "raw_text": payload.raw_text,
            "updated_at": now,
    }
    upsert_curriculum_config(
        camp_id=camp_id,
        update_doc=update_doc,
    )

    return config