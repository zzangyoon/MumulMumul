# app/tools/db_tools.py
from typing import List
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from app.core.schemas import Camp, User
from app.core.db import get_db

class camp_name_schema(BaseModel):
    camp_name: str = Field(..., description="캠프 이름의 일부 문자열")

class camp_id_schema(BaseModel):
    camp_id: int = Field(..., description="캠프 ID")

class camp_id_user_names_schema(BaseModel):
    camp_id: int = Field(..., description="캠프 ID")
    user_names: List[str] = Field(..., description="사용자 이름 리스트")

@tool(args_schema=camp_name_schema)
def get_camp_id_by_name(camp_name: str) -> int:
    """캠프 이름으로 camp_id 조회"""
    print(f"[TOOL] get_camp_id_by_name called: camp_name={camp_name}")

    db_gen = get_db()
    db = next(db_gen)
    try:
        camp = db.query(Camp).filter(Camp.name.contains(camp_name)).first()
        if not camp:
            raise ValueError(f"camp_name '{camp_name}' not found")

        print(f"[TOOL] get_camp_id_by_name result: camp_id={camp.camp_id}")
        return camp.camp_id
    finally:
        db.close()


@tool(args_schema=camp_id_schema)
def get_user_ids_by_camp_id(camp_id: int) -> List[int]:
    """캠프 ID로 해당 캠프의 모든 user_id 조회"""
    print(f"[TOOL] get_user_ids_by_camp_id called: camp_id={camp_id}")

    db_gen = get_db()
    db = next(db_gen)
    try:
        rows = db.query(User.user_id).filter(User.camp_id == camp_id).all()
        result = [r[0] for r in rows]

        print(f"[TOOL] get_user_ids_by_camp_id result: count={len(result)}")
        return result
    finally:
        db.close()


@tool(args_schema=camp_id_user_names_schema)
def resolve_user_ids_by_names(camp_id: int, user_names: List[str]) -> List[int]:
    """캠프 ID와 사용자 이름 리스트로 user_id 리스트 조회"""
    print(f"[TOOL] resolve_user_ids_by_names called: camp_id={camp_id}, user_names={user_names}")

    db_gen = get_db()
    db = next(db_gen)
    try:
        rows = (
            db.query(User.user_id)
            .filter(User.camp_id == camp_id)
            .filter(User.name.in_(user_names))
            .all()
        )
        result = [r[0] for r in rows]

        print(f"[TOOL] resolve_user_ids_by_names result: {result}")
        return result
    finally:
        db.close()
