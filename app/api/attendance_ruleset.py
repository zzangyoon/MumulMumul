# app/api/attendance_ruleset.py

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from pymongo.database import Database

from app.core.mongodb import get_mongo_db
from app.services.attendance.analysis_attendance_rule.llm import compile_ruleset_with_llm
from app.services.attendance.schemas import AttendanceRuleset, CompileRuleset
from app.services.db_service.attendance_ruleset import get_attendance_ruleset, save_attendance_ruleset

router = APIRouter()


class CreateRulesetRequest(BaseModel):
    camp_id: int
    raw_rules_text: str



@router.get("/{camp_id}")
def get_active_attendance_ruleset(
    camp_id: int,
    mongo: Database = Depends(get_mongo_db),
):
    attendance_ruleset = get_attendance_ruleset(mongo, camp_id)
    if not attendance_ruleset:
        return None

    return attendance_ruleset


@router.post("/generate")
def create_attendance_ruleset(
    payload: CreateRulesetRequest,
    mongo: Database = Depends(get_mongo_db),
):
    try:
        print("출결 규칙셋 LLM 컴파일 시작")
        rules: CompileRuleset = compile_ruleset_with_llm(payload.raw_rules_text)
    except Exception as e:
        print("출결 규칙셋 LLM 컴파일 실패")
        raise HTTPException(status_code=500, detail=str(e))

    try:
        print("출결 규칙셋 저장 중...")
        attendance_ruleset = save_attendance_ruleset(
            mongo,
            camp_id=payload.camp_id,
            raw_rules_text=payload.raw_rules_text,
            compiled_rules=rules.dict(),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return attendance_ruleset
