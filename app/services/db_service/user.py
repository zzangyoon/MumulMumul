
from app.core.db import get_db
from app.core.schemas import User

def get_user_by_id(user_id: int) -> User:
    """user_id로 사용자 조회"""
    db_gen = get_db()
    db = next(db_gen)
    try:
        user = db.query(User).filter(User.user_id == user_id).first()
        if not user:
            raise ValueError(f"user_id '{user_id}' not found")

        return user
    finally:
        db.close()

def get_tendancy_code_for_user(user_id: int) -> str:
    """사용자 성향 코드를 조회"""
    db_gen = get_db()
    db = next(db_gen)
    try:
        user = db.query(User).filter(User.user_id == user_id).first()
        if not user:
            raise ValueError(f"user_id '{user_id}' not found")

        return user.tendancy_code
    finally:
        db.close()