# app/api/attendance_ruleset.py

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from pymongo.database import Database

from app.core.mongodb import get_mongo_db
from app.services.attendance.analysis_attendance_rule.llm import compile_ruleset_with_llm
from app.services.db_service.attendance_ruleset import get_attendance_ruleset, save_attendance_ruleset

router = APIRouter(prefix="/attendance/ruleset", tags=["attendance-ruleset"])


class CreateRulesetRequest(BaseModel):
    camp_id: int
    name: str = Field(default="출결 규칙")
    raw_rules_text: str


class CreateRulesetResponse(BaseModel):
    ruleset_id: str
    is_active: bool
    compiled_rules: Dict[str, Any]


@router.get("/{camp_id}", response_model=Optional[CreateRulesetResponse])
def get_active_attendance_ruleset(
    camp_id: int,
    mongo: Database = Depends(get_mongo_db),
):
    doc = get_attendance_ruleset(camp_id)
    if not doc:
        return None

    return CreateRulesetResponse(
        ruleset_id=str(doc["_id"]),
        is_active=bool(doc.get("is_active", True)),
        compiled_rules=doc.get("compiled_rules", {}) or {},
    )


@router.post("", response_model=CreateRulesetResponse)
def create_attendance_ruleset(
    payload: CreateRulesetRequest,
    mongo: Database = Depends(get_mongo_db),
):
    try:
        rules = compile_ruleset_with_llm(payload.raw_rules_text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    try:
        ruleset_id = save_attendance_ruleset(
            camp_id=payload.camp_id,
            name=payload.name,
            raw_rules_text=payload.raw_rules_text,
            compiled_rules=rules,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return CreateRulesetResponse(
        ruleset_id=ruleset_id,
        is_active=True,
        compiled_rules=rules,
    )
