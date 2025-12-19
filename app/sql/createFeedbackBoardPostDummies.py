# app/sql/createFeedbackBoardPostDummies.py
import sys
from pathlib import Path

# 이 파일 기준으로 프로젝트 루트 계산
CURRENT_FILE = Path(__file__).resolve()
ROOT_DIR = CURRENT_FILE.parents[2]   # .../MumulMumul
sys.path.append(str(ROOT_DIR))
from pathlib import Path

from app.services.feedbackBoard.schemas import FeedbackBoardPost

# 이 파일 기준으로 프로젝트 루트 계산
CURRENT_FILE = Path(__file__).resolve()
ROOT_DIR = CURRENT_FILE.parents[2]   # .../MumulMumul
sys.path.append(str(ROOT_DIR))

import csv
import random
from datetime import datetime, timedelta, time

from pymongo import MongoClient
from sqlalchemy.orm import sessionmaker

from app.core.schemas import Camp, init_db
from app.config import MONGO_URL, MONGO_DB_NAME, SQLITE_URL


CSV_PATH = r"C:\Potenup\MumulMumul\app\sql\feedback_posts_125.csv"  # CSV 파일 경로


# ---------- 주차 기반 random datetime 생성 유틸 ----------
def random_datetime_in_week(camp: Camp | None, week_index: int) -> datetime:
    """
    camp.start_date / camp.end_date를 기준으로
    해당 주차 내 평일 랜덤 날짜 + 시간(09~18시, 15분 단위) 생성
    """
    if not camp or not camp.start_date or not camp.end_date:
        return datetime.utcnow()

    camp_start = camp.start_date.date()
    camp_end = camp.end_date.date()

    week_start_date = camp_start + timedelta(days=(week_index - 1) * 7)
    week_end_date = week_start_date + timedelta(days=6)

    effective_start = max(week_start_date, camp_start)
    effective_end = min(week_end_date, camp_end)

    if effective_start > effective_end:
        effective_start = camp_start
        effective_end = min(camp_start + timedelta(days=6), camp_end)

    candidate_days = []
    cur = effective_start
    while cur <= effective_end:
        if cur.weekday() < 5:
            candidate_days.append(cur)
        cur += timedelta(days=1)

    if not candidate_days:
        candidate_days = [effective_start]

    day = random.choice(candidate_days)
    hour = random.randint(9, 18)
    minute = random.choice([0, 15, 30, 45])

    return datetime.combine(day, time(hour, minute))


def insert_dummy_feedback_board_posts(
    camp_id_fixed: int = 1,
    collection_name: str = "feedback_board_posts",
):
    # --- SQLite 연결 (캠프 기간 조회용) ---
    engine = init_db(SQLITE_URL)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = SessionLocal()

    camps = {c.camp_id: c for c in db.query(Camp).all()}
    camp = camps.get(camp_id_fixed)

    # --- Mongo 연결 ---
    client = MongoClient(MONGO_URL)
    db_mongo = client[MONGO_DB_NAME]
    coll = db_mongo[collection_name]

    inserted_count = 0

    # --- CSV 읽기 ---
    with open(CSV_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            try:
                # CSV 필드
                user_id_raw = row.get("user_id", "").strip()
                week_index = 1
                content = (row.get("content") or "").strip()

                if not content:
                    continue

                created_at = random_datetime_in_week(camp, week_index)

                # user_id를 숫자로 쓰는 프로젝트면 여기서 변환 규칙을 정해줘야 함
                # 예: "user_201" -> 201
                if user_id_raw.startswith("user_"):
                    user_id = int(user_id_raw.split("_")[-1])
                else:
                    # 숫자 문자열이면 그대로
                    user_id = int(user_id_raw) if user_id_raw.isdigit() else 0

                # ---- feedback_board_posts에 저장할 최소 스키마(원문 전용) ----
                # 분석 결과(severity/is_toxic/category/sub_cluster/summary 등)는
                # analyzer가 별도 컬렉션/리포트에 생성한다고 가정
                doc = {
                    "camp_id": 1,
                    "user_id": user_id,
                    "content": content,             # 원문
                    "created_at": created_at,
                    "ai_analysis": None,
                }
                # doc = FeedbackBoardPost(
                #     camp_id=1,
                #     author_id=user_id,
                #     raw_text=content,
                #     created_at=created_at,
                #     ai_analysis=None,
                # )

                coll.insert_one(doc)
                inserted_count += 1

            except Exception as e:
                print(f"❌ Error inserting row: {row}")
                print(e)

    db.close()
    client.close()
    print(f"🎉 Done! Inserted {inserted_count} feedback board posts into '{collection_name}'.")


if __name__ == "__main__":
    insert_dummy_feedback_board_posts()