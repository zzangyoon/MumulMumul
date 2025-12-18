# 유저 타입이 운영진인 경우 이름을 "최자경"으로 일괄 변경
import sys
from pathlib import Path

# 이 파일 기준으로 프로젝트 루트 계산
CURRENT_FILE = Path(__file__).resolve()
ROOT_DIR = CURRENT_FILE.parents[2]   # .../MumulMumul

from app.config import SQLITE_URL
from app.core.schemas import User, init_db
from sqlalchemy.orm import sessionmaker

def update_admin_user_names():
    engine = init_db(SQLITE_URL)
    Session = sessionmaker(bind=engine, autoflush=False)
    session = Session()

    admin_users = session.query(User).filter(User.user_type_id == 1).all()
    for user in admin_users:
        user.name = "최자경"
    session.commit()

update_admin_user_names()