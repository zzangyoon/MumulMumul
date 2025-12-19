# app/core/schemas.py
from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from sqlalchemy import (
    Date,
    create_engine,
    Column,
    Integer,
    String,
    Text,
    DateTime,
    Boolean,
    ForeignKey,
    Float,
)
from enum import Enum
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

Base = declarative_base()


# ------------------------
# Camp DB
# ------------------------
class Camp(Base):
    __tablename__ = "camp"

    camp_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    total_weeks = Column(Integer, nullable=True)

    users = relationship("User", back_populates="camp")


# ------------------------
# User Type DB
# ------------------------
class UserType(Base):
    __tablename__ = "user_type"

    type_id = Column(Integer, primary_key=True, autoincrement=True)
    type_name = Column(String(100), nullable=False)
    permissions = Column(Text, nullable=True)  # 상세 권한 정보


# ------------------------
# User DB
# ------------------------
class User(Base):
    __tablename__ = "user"

    user_id = Column(Integer, primary_key=True, autoincrement=True)
    login_id = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=True)

    user_type_id = Column(Integer, ForeignKey("user_type.type_id"), nullable=False)
    camp_id = Column(Integer, ForeignKey("camp.camp_id"), nullable=True)

    tendency_completed = Column(Integer, nullable=False, default=0)  # 0 or 1
    tendency_type_code = Column(String(50), nullable=True, default=None)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    user_type = relationship("UserType")
    camp = relationship("Camp", back_populates="users")

# ------------------------
# Meetings DB
# ------------------------
class Meeting(Base):
    __tablename__ = "meeting"

    meeting_id = Column(String(255), primary_key=True)  # 회의 고유 ID (TEXT)
    title = Column(Text, nullable=False)
    organizer_id = Column(Integer, ForeignKey("user.user_id"), nullable=True)
    chat_room_id = Column(String(255), ForeignKey("chat_room.id"), nullable=False)

    start_time = Column(Text, nullable=False)  # ISO8601 string
    end_time = Column(Text, nullable=True)

    start_client_timestamp = Column(Integer, nullable=True)
    start_server_timestamp = Column(Integer, nullable=True)
    time_offset = Column(Integer, nullable=True)  # client - server 차이 (ms)

    status = Column(Text, nullable=True)  # in_progress / completed / cancelled ...

    agenda = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    participant_count = Column(Integer, nullable=True)

    created_at = Column(Text, nullable=True)
    updated_at = Column(Text, nullable=True)

    participants = relationship("MeetingParticipant", back_populates="meeting")
    organizer = relationship("User")
    room = relationship("ChatRoom", back_populates="meeting")


# ------------------------
# MeetingParticipants DB
# ------------------------
class MeetingParticipant(Base):
    __tablename__ = "meeting_participant"

    participant_id = Column(Integer, primary_key=True, autoincrement=True)
    meeting_id = Column(String(255), ForeignKey("meeting.meeting_id"), nullable=False)
    user_id = Column(Integer, ForeignKey("user.user_id"), nullable=False)

    join_time = Column(Integer, nullable=False)   # 입장 시간 (예: epoch ms)
    leave_time = Column(Integer, nullable=True)   # 퇴장 시간 (NULL이면 아직 참석 중)

    is_active = Column(Integer, nullable=True)    # 현재 활성 여부(0/1)
    role = Column(Text, nullable=True)            # 역할 (participant / host 등)
    is_voice_enabled = Column(Integer, nullable=True)
    is_chat_enabled = Column(Integer, nullable=True)

    created_at = Column(Text, nullable=True)      # 레코드 생성 시간

    meeting = relationship("Meeting", back_populates="participants")
    user = relationship("User")

# ------------------------
# session_activity_log
# (접속/세션 상태 기록)
# ------------------------
class AttendanceType(str, Enum):
    ON_TIME = "ON_TIME"
    LATE = "LATE"
    EARLY_LEAVE = "EARLY_LEAVE"
    ABSENT = "ABSENT"
    UNNORMAL_ACTIVITY = "UNNORMAL_ACTIVITY"
    # 아직 알수없는 상태
    UNKNOWN = "UNKNOWN"

class SessionActivityLog(Base):
    __tablename__ = "session_activity_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    camp_id = Column(Integer, nullable=False)
    user_id = Column(Integer, ForeignKey("user.user_id"), nullable=False)
    date= Column(Date, nullable=False, default=datetime.utcnow().date())
    join_at = Column(DateTime, nullable=True) 
    leave_at = Column(DateTime, nullable=True) 

    user = relationship("User")

class AttendanceDaily(Base):
    __tablename__ = "attendance_daily"

    id = Column(Integer, primary_key=True, autoincrement=True)

    camp_id = Column(Integer, nullable=False, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    is_finalized = Column(Boolean, nullable=False, default=False)

    # ON_TIME / LATE / EARLY_LEAVE / ABSENT
    attendance_type = Column(String(10), nullable=True, index=True)
    total_active_time= Column(Integer, nullable=True)  # 총 접속 시간 (분 단위)
    first_join= Column(DateTime, nullable=True)
    last_leave= Column(DateTime, nullable=True)
    never_joined= Column(Boolean, nullable=True, default=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

# ------------------------
# STT Segment DB
# ------------------------
class STTSegment(Base):
    """
    STT 처리된 세그먼트 (겹침 처리 지원)
    """
    __tablename__ = "stt_segment"
    
    # PK
    segment_id = Column(String(255), primary_key=True)
    
    # FK
    meeting_id = Column(String(255), ForeignKey("meeting.meeting_id"), nullable=False)
    user_id = Column(Integer, ForeignKey("user.user_id"), nullable=False)
    
    # 청크 정보
    chunk_index = Column(Integer, nullable=False)
    
    # STT 결과
    text = Column(Text, nullable=False)
    confidence = Column(Float, nullable=True, default=0.0)
    
    # 타이밍 정보
    start_time_ms = Column(Integer, nullable=False)
    end_time_ms = Column(Integer, nullable=False)
    
    # 겹침 처리 정보
    source_chunks = Column(String(255), nullable=True)  # "0", "0,1", "1,2" 형태
    is_overlapped = Column(Boolean, nullable=True, default=False)
    
    # 메타데이터
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # 관계
    meeting = relationship("Meeting")
    user = relationship("User")
    
    def __repr__(self):
        return f"<STTSegment {self.segment_id}: '{self.text[:50]}' overlap={self.is_overlapped}>"

# ------------------------
# Team Chat Room DB
# ------------------------
class ChatRoom(Base):
    __tablename__ = "chat_room"

    id = Column(String(255), primary_key=True)  # teamChatId (예: "team_001")
    name = Column(String(255), nullable=False)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    members = relationship("ChatRoomUser", back_populates="room")
    meeting = relationship("Meeting", back_populates="room")


class ChatRoomUser(Base):
    __tablename__ = "chat_room_user"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_room_id = Column(String(255), ForeignKey("chat_room.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("user.user_id"), nullable=False)

    # 역할 같은 메타정보 필요하면 여기에 추가 가능 (예: is_admin 등)

    room = relationship("ChatRoom", back_populates="members")
    user = relationship("User")

# ================================
# 운영진 공지/DM DB
# ================================
# 공지/DM 로그 저장
class NoticeLog(Base):
    __tablename__ = "notice_log"
    id = Column(Integer, primary_key=True, autoincrement=True)
    camp_id = Column(Integer, nullable=False)
    Recipient_id = Column(Integer, ForeignKey("user.user_id"), nullable=False)
    Sender_id = Column(Integer, ForeignKey("user.user_id"), nullable=True)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    is_need_confirmation = Column(Boolean, default=False, nullable=False)

    sender = relationship("User", foreign_keys=[Sender_id])

# 유저가 체크 했는지 여부
class NoticeConfirmation(Base):
    __tablename__ = "notice_confirmation"
    id = Column(Integer, primary_key=True, autoincrement=True)
    notice_id= Column(Integer, ForeignKey("notice_log.id"), nullable=False)
    camp_id = Column(Integer, nullable=False)
    user_id = Column(Integer, ForeignKey("user.user_id"), nullable=False)
    is_confirmed = Column(Boolean, default=False, nullable=False)
    confirmed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    notice = relationship("NoticeLog", foreign_keys=[notice_id])

# =====================================
# DB 초기화 함수
# =====================================
def init_db(db_url: str = "sqlite:///mumul.db"):
    engine = create_engine(db_url, echo=True, future=True)
    Base.metadata.create_all(engine)
    return engine


if __name__ == "__main__":
    engine = init_db()
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with SessionLocal() as session:
        print("DB initialized. Table list:", engine.table_names())
