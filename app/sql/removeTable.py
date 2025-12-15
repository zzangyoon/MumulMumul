import sys
from pathlib import Path

# 이 파일 기준으로 프로젝트 루트 계산
CURRENT_FILE = Path(__file__).resolve()
ROOT_DIR = CURRENT_FILE.parents[2]   # .../MumulMumul

from sqlalchemy import create_engine, text

def drop_camp_table(table_name, db_url="sqlite:///storage/mumul.db"):
    print(f"{table_name} 테이블 삭제 준비")
    engine = create_engine(db_url, echo=True, future=True)
    with engine.connect() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS {table_name}"))
        conn.commit()
        print(f"{table_name} 테이블 삭제 완료")

drop_camp_table("camp")
drop_camp_table("user")
drop_camp_table("user_type")
