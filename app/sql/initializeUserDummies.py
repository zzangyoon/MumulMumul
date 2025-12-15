import sys
from pathlib import Path

# 이 파일 기준으로 프로젝트 루트 계산
CURRENT_FILE = Path(__file__).resolve()
ROOT_DIR = CURRENT_FILE.parents[2]   # .../MumulMumul

sys.path.append(str(ROOT_DIR))

from sqlalchemy.orm import sessionmaker
from app.core.schemas import UserType, User, Camp, init_db
from app.config import SQLITE_URL
from datetime import datetime, timedelta, time

# 모든 User 더미 데이터의 tendency_completed = 0	tendency_type_code = Null 로 초기화
def initialize_user_dummies():
    SessionLocal = sessionmaker(bind=init_db(SQLITE_URL))
    db = SessionLocal()

    users = db.query(User).all()
    for user in users:
        user.tendency_completed = 0
        user.tendency_type_code = None
    db.commit()
    db.close()
    print("Initialized all user dummies: tendency_completed set to 0 and tendency_type_code set to Null.")

if __name__ == "__main__":
    initialize_user_dummies()