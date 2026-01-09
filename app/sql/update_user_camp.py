import sys
from pathlib import Path

# 이 파일 기준으로 프로젝트 루트 계산
CURRENT_FILE = Path(__file__).resolve()
ROOT_DIR = CURRENT_FILE.parents[2]   # .../MumulMumul

sys.path.append(str(ROOT_DIR))

from sqlalchemy.orm import sessionmaker
from app.core.schemas import User, init_db
from app.config import SQLITE_URL


def update_user_camp(user_id: int, camp_id: int) -> bool:
    """
    user_id가 n인 사용자의 camp_id를 변경
    성공 시 True, 실패(유저 없음) 시 False 반환
    """
    engine = init_db(SQLITE_URL)
    Session = sessionmaker(bind=engine, autoflush=False)
    session = Session()

    try:
        user = session.query(User).filter(User.user_id == user_id).first()

        if not user:
            print(f"user_id={user_id} 인 사용자를 찾을 수 없습니다.")
            return False

        old_camp_id = user.camp_id
        user.camp_id = camp_id
        session.commit()

        print(f"사용자 camp_id 변경 완료: user_id={user_id}, {old_camp_id} -> {camp_id}")
        return True

    except Exception as e:
        session.rollback()
        print("camp_id 변경 중 오류 발생:", e)
        return False

    finally:
        session.close()


if __name__ == "__main__":
    # 사용 예시
    update_user_camp(user_id=11, camp_id=1)
    update_user_camp(user_id=12, camp_id=1)
    update_user_camp(user_id=13, camp_id=1)
    update_user_camp(user_id=14, camp_id=1)
    update_user_camp(user_id=15, camp_id=1)
    update_user_camp(user_id=16, camp_id=1)
    update_user_camp(user_id=17, camp_id=1)
    update_user_camp(user_id=18, camp_id=1)
    update_user_camp(user_id=19, camp_id=1)
