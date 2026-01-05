import sys
from pathlib import Path

# 이 파일 기준으로 프로젝트 루트 계산
CURRENT_FILE = Path(__file__).resolve()
ROOT_DIR = CURRENT_FILE.parents[2]   # .../MumulMumul

sys.path.append(str(ROOT_DIR))

from sqlalchemy.orm import sessionmaker
from app.core.schemas import User, init_db
from app.config import SQLITE_URL


def update_user_name(user_id: int, new_name: str) -> bool:
    """
    user_id가 n인 사용자의 이름을 new_name으로 변경
    성공 시 True, 실패(유저 없음) 시 False 반환
    """
    engine = init_db(SQLITE_URL)
    Session = sessionmaker(bind=engine, autoflush=False)
    session = Session()

    try:
        user = session.query(User).filter(User.user_id == user_id).first()

        if not user:
            print(f"❌ user_id={user_id} 인 사용자를 찾을 수 없습니다.")
            return False

        old_name = user.name
        user.name = new_name
        session.commit()

        print(f"✅ 사용자 이름 변경 완료: {old_name} → {new_name}")
        return True

    except Exception as e:
        session.rollback()
        print("🔥 이름 변경 중 오류 발생:", e)
        return False

    finally:
        session.close()

if __name__ == "__main__":
    update_user_name(user_id=5, new_name="윤여민")
    update_user_name(user_id=6, new_name="김해찬")
