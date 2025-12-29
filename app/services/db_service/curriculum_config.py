from datetime import datetime
from typing import Optional
from pymongo.database import Database

from app.core.mongodb import CurriculumConfig
from app.core.mongodb import get_mongo_db

mongo_db: Database = get_mongo_db()
curriculum_col = mongo_db["curriculum_configs"]

def get_curriculum_config_for_camp(camp_id: int) -> Optional[CurriculumConfig]:
    doc = curriculum_col.find_one({"camp_id": camp_id})
    if not doc:
        return None
    doc.pop("_id", None)
    return CurriculumConfig(**doc)


def upsert_curriculum_config(
    camp_id: int,
    update_doc: dict,
) -> None:
    now = datetime.utcnow()

    if "created_at" in update_doc:
        del update_doc["created_at"]
    
    # 만약 raw_text 필드가 없다면 기존 문서에서 가져와서 유지
    if "raw_text" not in update_doc:
        existing_doc = curriculum_col.find_one({"camp_id": camp_id}, {"raw_text": 1})
        if existing_doc and "raw_text" in existing_doc:
            update_doc["raw_text"] = existing_doc["raw_text"]

    curriculum_col.update_one(
        {"camp_id": camp_id},
        {
            "$set": update_doc,
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )