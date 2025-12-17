# app/api/team_chat_router.py

from typing import List
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.mongodb import get_mongo_db

from app.core.schemas import User, ChatRoom, ChatRoomUser
from app.core.timezone import datetime_to_custom_str, datetime_to_iso_milliseconds

mongo_db = get_mongo_db()
collection = mongo_db["team_chat_messages"]

# ====================================
#  Pydantic Schemas
# ====================================

class TeamChatUser(BaseModel):
    userId: int
    userName: str


class TeamChatRoomResponse(BaseModel):
    teamChatId: str
    teamName: str
    users: List[TeamChatUser]


class ChatMessageResponse(BaseModel):
    chatId: str
    userId: int
    userName: str
    message: str
    createdAt: str  # ISO8601 문자열
    formattedCreatedAt: str = None  # "2025년 12월 31일 오후 11:59" 형식


class ChatMessageCreate(BaseModel):
    userId: int
    message: str
    createdAt: str  # 클라이언트 타임스탬프


class TeamChatRoomCreate(BaseModel):
    groupName: str
    userIdList: List[int]


class TeamChatRoomCreatedResponse(BaseModel):
    groupId: str
    groupName: str
    userIdList: List[int]


router = APIRouter()

# ==========================================================
# 1) 채팅방 리스트 요청 : GET /chat/rooms
# ==========================================================

@router.get("/rooms", response_model=List[TeamChatRoomResponse])
def get_team_chat_rooms(userId: int, db: Session = Depends(get_db)):
    """
    로그인한 사용자가 참여하고 있는 모든 팀 채팅방 정보 조회
    """

    user = db.query(User).filter(User.user_id == userId).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorCode": "USER_NOT_FOUND",
                "message": "해당 userId를 찾을 수 없습니다.",
            },
        )

    # ChatRoomUser 를 통해 해당 유저가 속한 방들 조회
    room_users = (
        db.query(ChatRoomUser)
        .filter(ChatRoomUser.user_id == userId)
        .all()
    )
    room_ids = [ru.chat_room_id for ru in room_users]

    if not room_ids:
        return []

    rooms = db.query(ChatRoom).filter(ChatRoom.id.in_(room_ids)).all()

    # 각 방별로 멤버 조회
    responses: List[TeamChatRoomResponse] = []
    for room in rooms:
        members = (
            db.query(ChatRoomUser)
            .filter(ChatRoomUser.chat_room_id == room.id)
            .all()
        )

        users = [
            TeamChatUser(
                userId=m.user_id,
                userName=m.user.name if m.user else "",
            )
            for m in members
        ]

        responses.append(
            TeamChatRoomResponse(
                teamChatId=room.id,
                teamName=room.name,
                users=users,
            )
        )

    return responses


# ==========================================================
# 2) 채팅방 채팅 기록 조회 : GET /chat/rooms/{teamChatId}/messages
# ==========================================================

@router.get(
    "/rooms/{teamChatId}/messages",
    response_model=List[ChatMessageResponse],
)
def get_team_chat_messages(
    teamChatId: str,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """
    특정 채팅방의 채팅 기록 조회
    - 방 존재 여부는 SQLite(ChatRoom)로 확인
    - 메시지 데이터는 MongoDB 에서 조회
    """

    room = db.query(ChatRoom).filter(ChatRoom.id == teamChatId).first()
    if room is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorCode": "CHAT_ROOM_NOT_FOUND",
                "message": "해당 채팅방을 찾을 수 없습니다.",
            },
        )

    cursor = (
        collection.find({"roomId": teamChatId})
        .sort("createdAt", 1)
        .skip(offset)
        .limit(limit)
    )

    results: List[ChatMessageResponse] = []
    for doc in cursor:
        results.append(
            ChatMessageResponse(
                chatId=str(doc["_id"]),
                userId=doc["userId"],
                userName=doc.get("userName", ""),
                message=doc["message"],
                createdAt=datetime_to_iso_milliseconds(doc["createdAt"]),
                formattedCreatedAt=datetime_to_custom_str(doc["createdAt"])
            ))
        

    return results


# ==========================================================
# 3) 채팅 메시지 전송(저장) : POST /chat/rooms/{teamChatId}/messages
# ==========================================================

@router.post(
    "/rooms/{teamChatId}/messages",
    response_model=ChatMessageResponse,
)
def post_team_chat_message(
    teamChatId: str,
    payload: ChatMessageCreate,
    db: Session = Depends(get_db),
):
    """
    특정 채팅방에 메시지 저장
    - 방 존재 여부는 SQLite(ChatRoom)에서 확인
    - 메시지는 MongoDB 컬렉션에 insert
    """

    room = db.query(ChatRoom).filter(ChatRoom.id == teamChatId).first()
    if room is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorCode": "CHAT_ROOM_NOT_FOUND",
                "message": "해당 채팅방을 찾을 수 없습니다.",
            },
        )

    user = db.query(User).filter(User.user_id == payload.userId).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorCode": "USER_NOT_FOUND",
                "message": "해당 userId를 찾을 수 없습니다.",
            },
        )

    doc = {
        "roomId": teamChatId,
        "type": "team",
        "userId": payload.userId,
        "userName": user.name,
        "message": payload.message,
        "createdAt": datetime.now(timezone.utc)
    }

    result = collection.insert_one(doc)

    return ChatMessageResponse(
        chatId=str(result.inserted_id),
        userId=payload.userId,
        userName=user.name,
        message=payload.message,
        createdAt=payload.createdAt,
        formattedCreatedAt=datetime_to_custom_str(doc["createdAt"])
    )


# ==========================================================
# 4) 팀 채팅방 생성 : POST /chat/rooms
# ==========================================================

@router.post(
    "/rooms",
    response_model=TeamChatRoomCreatedResponse,
)
def create_team_chat_room(
    payload: TeamChatRoomCreate,
    db: Session = Depends(get_db),
):
    """
    팀 채팅방 생성 (SQLite에 방/멤버 저장)
    """

    if not payload.userIdList:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "errorCode": "INVALID_USER_LIST",
                "message": "userIdList가 비어 있습니다.",
            },
        )

    # 유저 유효성 체크
    users = (
        db.query(User)
        .filter(User.user_id.in_(payload.userIdList))
        .all()
    )
    if len(users) != len(payload.userIdList):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "errorCode": "INVALID_USER_LIST",
                "message": "userIdList에 유효하지 않은 유저가 포함되어 있습니다.",
            },
        )

    # 간단히 UUID 대신 groupName 기반으로 id 생성해도 되고,
    # 실제 서비스에서는 uuid4 사용 권장.
    import uuid
    room_id = f"team_{uuid.uuid4().hex[:8]}"

    new_room = ChatRoom(
        id=room_id,
        name=payload.groupName,
    )
    db.add(new_room)
    db.commit()
    db.refresh(new_room)

    # 멤버 추가
    for uid in payload.userIdList:
        rel = ChatRoomUser(chat_room_id=new_room.id, user_id=uid)
        db.add(rel)
    db.commit()

    return TeamChatRoomCreatedResponse(
        groupId=new_room.id,
        groupName=new_room.name,
        userIdList=payload.userIdList,
    )
