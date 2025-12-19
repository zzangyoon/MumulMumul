# app/services/db_service/attendance_ruleset.py

from __future__ import annotations

from datetime import datetime
from typing import Optional

from bson import ObjectId
from pymongo.database import Database

from app.services.attendance.schemas import AttendanceRuleset, CompileRuleset


COLLECTION_NAME = "attendance_ruleset"


def _to_ruleset_model(doc: dict) -> AttendanceRuleset:
    """
    Mongo 문서(dict) -> AttendanceRuleset(BaseModel)로 변환
    """
    return AttendanceRuleset(
        ruleset_id=str(doc["_id"]),
        camp_id=int(doc["camp_id"]),
        raw_text=doc.get("raw_text") or doc.get("raw_rules_text") or "",
        compiled_rules=doc.get("compiled_rules") or {},
        is_active=bool(doc.get("is_active", True)),
        created_at=doc.get("created_at") or datetime.utcnow(),
        updated_at=doc.get("updated_at") or datetime.utcnow(),
    )


def get_attendance_ruleset(mongo: Database, camp_id: int) -> Optional[AttendanceRuleset]:
    """
    camp_id에 해당하는 active 출결 규칙 반환. 없으면 None.
    """
    col = mongo[COLLECTION_NAME]
    doc = col.find_one({"camp_id": camp_id, "is_active": True})
    if not doc:
        return None
    return _to_ruleset_model(doc)


def save_attendance_ruleset(
    mongo: Database,
    camp_id: int,
    raw_rules_text: str,
    compiled_rules: CompileRuleset,
) -> AttendanceRuleset:
    """
    attendance_ruleset 문서 저장.
    - 같은 camp_id의 기존 is_active=True 문서는 false로 내림
    - 새 ruleset을 is_active=True로 저장
    """
    col = mongo[COLLECTION_NAME]
    now = datetime.utcnow()

    # 1) 기존 active 문서가 있으면 비활성화
    col.update_many(
        {"camp_id": camp_id, "is_active": True},
        {"$set": {"is_active": False, "updated_at": now}},
    )

    # 2) compiled_rules는 Mongo-safe dict로 변환
    compiled_dict = (
        compiled_rules.model_dump(mode="json")
        if hasattr(compiled_rules, "model_dump")
        else compiled_rules
    )

    # 3) 새 문서 insert
    insert_doc = {
        "camp_id": camp_id,
        "raw_text": raw_rules_text,
        "compiled_rules": compiled_dict,
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    }
    result = col.insert_one(insert_doc)

    # 4) 저장된 문서 읽어서 모델로 반환
    saved = col.find_one({"_id": result.inserted_id})
    return _to_ruleset_model(saved)
