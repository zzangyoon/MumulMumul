from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.schemas import Camp, User

router = APIRouter()

@router.get("/")
def list_camps(db: Session = Depends(get_db)):
    """
    캠프(반) 목록 조회 API
    - 별도 Pydantic 모델 없이 dict 리스트로 리턴
    """
    camps = db.query(Camp).order_by(Camp.camp_id.asc()).all()
    return {
        "camps": camps
    }


@router.get("/{camp_id}/students")
def list_students_by_camp(
    camp_id: int,
    db: Session = Depends(get_db),
):
    """
    특정 캠프(반)의 유저(학생) 목록 조회 API
    - 이것도 dict 리스트로 심플하게
    """
    camp = db.query(Camp).filter(Camp.camp_id == camp_id).first()
    if not camp:
        raise HTTPException(status_code=404, detail="캠프를 찾을 수 없음")

    users = (
        db.query(User)
        .filter(User.camp_id == camp_id)
        .order_by(User.user_id.asc())
        .all()
    )

    result = []
    for u in users:
        result.append(
            {
                "user_id": u.user_id,
                "name": u.name,
                "login_id": u.login_id,
                "email": u.email,
                "camp_id": u.camp_id,
            }
        )
    return result