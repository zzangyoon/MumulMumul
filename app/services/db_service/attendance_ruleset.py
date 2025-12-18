# -----------------------------
# MongoDB Save
# -----------------------------
from datetime import datetime
from typing import Dict, Any

from app.core.mongodb import get_mongo_db
from app.services.attendance.schemas import AttendanceRuleset

mongo = get_mongo_db()
col = mongo["attendance_ruleset"]

def get_attendance_ruleset(camp_id: int) -> AttendanceRuleset | None:
    """
    camp_id에 해당하는 active 출결 규칙을 반환.
    - 없으면 None 반환
    """

    doc = col.find_one({"camp_id": camp_id, "is_active": True})
    if not doc:
        return None

    return doc

def save_attendance_ruleset(
    camp_id: int,
    name: str,
    raw_rules_text: str,
    compiled: Dict[str, Any],
) -> str:
    """
    attendance_ruleset 문서 저장.
    - 같은 camp_id의 기존 is_active=True 문서는 false로 내림
    - 새 ruleset을 is_active=True로 저장
    """    

    # 기존 active ruleset 비활성화
    col.update_many(
        {"camp_id": camp_id, "is_active": True},
        {"$set": {"is_active": False, "updated_at": datetime.utcnow()}},
    )

    doc = {
        "camp_id": camp_id,
        "name": name,
        "raw_rules_text": raw_rules_text,
        "compiled_rules": compiled,
        "compile_warnings": compiled.get("compile_warnings", []),
        "needs_clarification": bool(compiled.get("needs_clarification", False)),
        "is_active": True,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }

    res = col.insert_one(doc)
    return str(res.inserted_id)