import sys
from pathlib import Path

# 이 파일 기준으로 프로젝트 루트 계산
CURRENT_FILE = Path(__file__).resolve()
ROOT_DIR = CURRENT_FILE.parents[2]   # .../MumulMumul

sys.path.append(str(ROOT_DIR))

from sqlalchemy.orm import sessionmaker
from app.core.schemas import ChatRoomUser, init_db
from app.config import SQLITE_URL


def insert_chat_room_user(chat_room_id: str, user_id: int) -> bool:
    """
    chat_room_user 테이블에 새로운 레코드 추가
    성공 시 True, 실패 시 False 반환
    """
    engine = init_db(SQLITE_URL)
    Session = sessionmaker(bind=engine, autoflush=False)
    session = Session()

    try:
        # 중복 체크
        existing = session.query(ChatRoomUser).filter(
            ChatRoomUser.chat_room_id == chat_room_id,
            ChatRoomUser.user_id == user_id
        ).first()

        if existing:
            print(f"이미 존재하는 레코드입니다: chat_room_id={chat_room_id}, user_id={user_id}")
            return False

        new_record = ChatRoomUser(
            chat_room_id=chat_room_id,
            user_id=user_id
        )
        session.add(new_record)
        session.commit()

        print(f"chat_room_user 추가 완료: chat_room_id={chat_room_id}, user_id={user_id}")
        return True

    except Exception as e:
        session.rollback()
        print("chat_room_user 추가 중 오류 발생:", e)
        return False

    finally:
        session.close()


def insert_chat_room_users_batch(chat_room_id: str, user_ids: list) -> int:
    """
    여러 user_id를 한 번에 추가
    성공한 개수 반환
    """
    success_count = 0
    for user_id in user_ids:
        if insert_chat_room_user(chat_room_id, user_id):
            success_count += 1

    print(f"배치 추가 완료: {success_count}/{len(user_ids)} 건 성공")
    return success_count


if __name__ == "__main__":
    # 사용 예시 - 단일 추가
    # insert_chat_room_user(chat_room_id="team_474850ae", user_id=12)

    # 사용 예시 - 배치 추가
    insert_chat_room_users_batch(chat_room_id="team_474850ae", user_ids=[15, 16, 17, 18, 19, 20])
