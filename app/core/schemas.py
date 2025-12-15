# app/core/schemas.py
from datetime import datetime
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
    Enum
)
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
    tendency_type_code = Column(String(50), nullable=True)

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
class SessionActivityLog(Base):
    __tablename__ = "session_activity_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("user.user_id"), nullable=False)
    join_at = Column(DateTime, nullable=True) 
    leave_at = Column(DateTime, nullable=True) 

    user = relationship("User")

attendance_status_enum = Enum(
    "정상",
    "지각",
    "조퇴",
    "결석",
    "부분참여",
    name="attendance_status_enum",
)

class DailyAttendance(Base):
    __tablename__ = "daily_attendance"

    id = Column(Integer, primary_key=True, autoincrement=True)

    camp_id = Column(Integer, ForeignKey("camp.camp_id"), nullable=False)
    user_id = Column(Integer, ForeignKey("user.user_id"), nullable=False)
    date = Column(Date, nullable=False)

    total_minutes = Column(Integer, nullable=False)
    morning_minutes = Column(Integer, nullable=False, default=0)   # 9–12
    afternoon_minutes = Column(Integer, nullable=False, default=0) # 13–18

    status = Column(attendance_status_enum, nullable=False)
    note = Column(String(255), nullable=True)

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
