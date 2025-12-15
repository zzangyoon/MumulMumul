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


def seed_dummy_data():
    engine = init_db(SQLITE_URL)
    Session = sessionmaker(bind=engine, autoflush=False)
    session = Session()

    ai_camp = Camp(name="AI 캠프", start_date=datetime(2025, 11, 3), end_date=datetime(2025, 11, 3) + timedelta(weeks=6), total_weeks=6)
    test_camp = Camp(name="머물머물 캠프", start_date=datetime(2025, 11, 3), end_date=datetime(2025, 11, 3) + timedelta(weeks=6), total_weeks=6)

    session.add_all([test_camp, ai_camp])
    session.commit()

seed_dummy_data()