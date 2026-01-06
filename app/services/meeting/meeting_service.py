import uuid
from typing import Dict
from datetime import datetime
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.core.logger import setup_logger
from app.core.schemas import Meeting, MeetingParticipant, User, STTSegment
from app.core.timezone import get_current_timestamp, get_current_datetime, format_datetime
from app.services.meeting.schemas import (
    StartMeetingRequest, 
    StartMeetingResponse,
    JoinMeetingRequest,
    JoinMeetingResponse,
    EndMeetingResponse
)

logger = setup_logger(__name__)


class MeetingService:
    """회의 관련 비즈니스 로직"""
    
    # 회의 시작
    @staticmethod
    def start_meeting(
        request: StartMeetingRequest,
        db: Session
    ) -> StartMeetingResponse:
        try:
            logger.info("="*60)
            logger.info(
                f"Starting new meeting\n"
                f"team_id: {request.chat_room_id}\n"
                f"Title: {request.title}\n"
                f"Organizer: {request.organizer_id}\n"
                f"timestamp: {request.client_timestamp}"
            )
            logger.info("="*60)
            
            # 1. meeting_id 생성
            date_str = datetime.now().strftime("%y%m%d")
            short_uuid = uuid.uuid4().hex[:5]
            meeting_id = f"{date_str}_{short_uuid}"
            logger.info(f"Generated meeting_id: {meeting_id}")
            
            # 2. 시간 동기화
            server_timestamp = get_current_timestamp()
            time_offset = request.client_timestamp - server_timestamp
            logger.info(
                f"Time synchronization:\n"
                f"  Client: {request.client_timestamp}\n"
                f"  Server: {server_timestamp}\n"
                f"  Offset: {time_offset}ms"
            )
            
            current_dt = get_current_datetime()
            start_time_iso = format_datetime(current_dt, "%Y-%m-%dT%H:%M:%S%z")     # iso 시간
            
            # 3. 주최자 확인
            organizer = db.query(User).filter(
                User.user_id == request.organizer_id
            ).first()
            
            if not organizer:
                raise ValueError(f"Organizer not found: {request.organizer_id}")
            
            logger.info(f"Organizer: {organizer.name} (ID: {organizer.user_id})")
            
            # 4. Meeting 생성
            new_meeting = Meeting(
                meeting_id = meeting_id,
                title = request.title,
                organizer_id = request.organizer_id,
                chat_room_id = request.chat_room_id,
                start_time = start_time_iso,
                end_time = None,
                start_client_timestamp = request.client_timestamp,
                start_server_timestamp = server_timestamp,
                time_offset = time_offset,
                status = "in_progress",
                agenda = request.agenda,
                description = request.description,
                duration_ms = None,
                participant_count = 1,  # 주최자
                created_at = start_time_iso,
                updated_at = start_time_iso
            )
            
            db.add(new_meeting)
            db.flush()
            
            logger.info(f"Meeting created: {meeting_id}")
            
            # 5. 주최자를 참가자로 추가
            organizer_participant = MeetingParticipant(
                meeting_id = meeting_id,
                user_id = request.organizer_id,
                join_time = server_timestamp,   # 회의 시작 시간 = 주최자 입장 시간
                leave_time = None,
                is_active = 1,
                role = "host",
                is_voice_enabled = 1,
                is_chat_enabled = 0,
                created_at = start_time_iso
            )
            
            db.add(organizer_participant)
            db.commit()
            
            logger.info(f"Organizer added as participant: {meeting_id}")
            
            return StartMeetingResponse(
                meeting_id = meeting_id,
                status="in_progress"
            )
        
        except Exception as e:
            logger.error(f"Failed to start meeting: {e}", exc_info=True)
            db.rollback()
            raise
    
    # 회의 참가
    @staticmethod
    def join_meeting(
        meeting_id: str,
        request: JoinMeetingRequest,
        db: Session
    ) -> JoinMeetingResponse:
        try:
            logger.info(f"User {request.user_id} joining meeting {meeting_id}")
            
            # 1. 회의 확인
            meeting = db.query(Meeting).filter(
                Meeting.meeting_id == meeting_id
            ).first()
            
            if not meeting:
                raise ValueError(f"Meeting not found: {meeting_id}")
            
            if meeting.status != "in_progress":
                raise ValueError(f"Meeting not in progress: {meeting.status}")
            
            # 2. 사용자 확인
            user = db.query(User).filter(
                User.user_id == request.user_id
            ).first()
            
            if not user:
                raise ValueError(f"User not found: {request.user_id}")
            
            # 3. 중복 참가 체크
            existing = db.query(MeetingParticipant).filter(
                MeetingParticipant.meeting_id == meeting_id,
                MeetingParticipant.user_id == request.user_id,
                MeetingParticipant.is_active == 1
            ).first()
            
            if existing:
                logger.warning(f"User {request.user_id} already in meeting")
                return JoinMeetingResponse(
                    participant_id = existing.participant_id,
                    meeting_id = meeting_id,
                    user_id = request.user_id
                )
            
            # 4. 참가자 추가
            current_dt = get_current_datetime()
            created_at_iso = format_datetime(current_dt, "%Y-%m-%dT%H:%M:%S%z")
            
            participant = MeetingParticipant(
                meeting_id = meeting_id,
                user_id = request.user_id,
                join_time = request.client_timestamp,  # 클라이언트 시간
                leave_time = None,
                is_active = 1,
                role = "participant",
                is_voice_enabled = 1,
                is_chat_enabled = 0,
                created_at = created_at_iso
            )
            
            db.add(participant)
            
            # 5. participant_count 증가 (동시성 안전)
            db.execute(
                text("""
                    UPDATE meeting 
                    SET participant_count = participant_count + 1 
                    WHERE meeting_id = :meeting_id
                """),
                {"meeting_id": meeting_id}
            )
            db.commit()

            logger.info(
                f"User {user.name} joined meeting\n"
                f"  Join time: {request.client_timestamp}\n"
                f"  Meeting start: {meeting.start_client_timestamp}\n"
                f"  Offset: {request.client_timestamp - meeting.start_client_timestamp}ms"
            )
            
            return JoinMeetingResponse(
                participant_id=participant.participant_id,
                meeting_id=meeting_id,
                user_id=request.user_id
            )
        
        except Exception as e:
            logger.error(f"Failed to join meeting: {e}", exc_info=True)
            db.rollback()
            raise
    
    # 회의 종료중
    @staticmethod
    async def end_meeting(
        meeting_id: str,
        db: Session
    ) -> EndMeetingResponse:
        try:
            logger.info("="*60)
            logger.info(f"Ending meeting: {meeting_id}")
            logger.info("="*60)
            
            # 1. 회의 확인
            meeting = db.query(Meeting).filter(
                Meeting.meeting_id == meeting_id
            ).first()
            
            if not meeting:
                raise ValueError(f"Meeting not found: {meeting_id}")
            
            if meeting.status != "in_progress":
                raise ValueError(f"Meeting not in progress: {meeting.status}")
            
            # 2. 시간 계산
            end_timestamp = get_current_timestamp()
            end_dt = get_current_datetime()
            end_time_iso = format_datetime(end_dt, "%Y-%m-%dT%H:%M:%S%z")
            
            duration_ms = end_timestamp - meeting.start_server_timestamp
            
            logger.info(f"Duration: {duration_ms}ms ({duration_ms/60000:.2f} min)")
            
            # 3. 회의 상태 업데이트
            meeting.status = "ending"
            meeting.end_time = end_time_iso
            meeting.duration_ms = duration_ms
            meeting.updated_at = end_time_iso
            
            # 4. 모든 참가자 퇴장 처리
            db.execute(
                text("""
                    UPDATE meeting_participant 
                    SET leave_time = :leave_time, is_active = 0 
                    WHERE meeting_id = :meeting_id AND is_active = 1
                """),
                {"leave_time": end_timestamp, "meeting_id": meeting_id}
            )
            
            # 5. STT Segment 개수 확인
            total_segments = db.query(STTSegment).filter(
                STTSegment.meeting_id == meeting_id
            ).count()
            
            db.commit()
            
            logger.info(
                f"Meeting ended\n"
                f"  Duration: {duration_ms}ms"
                f"  Participants: {meeting.participant_count}"
                f"  Segments: {total_segments}"
            )

            return EndMeetingResponse(
                meeting_id = meeting_id,
                status = "ending",
                duration_ms = duration_ms,
                participant_count = meeting.participant_count,
                total_segments = total_segments
                # waited_for_processing = wait_result["waited_for_processing"],
                # wait_time_ms = wait_result["wait_time_ms"]
            )
        
        except Exception as e:
            logger.error(f"Failed to end meeting: {e}", exc_info=True)
            db.rollback()
            raise


    # 회의 최종 종료 (백그라운드용)
    @staticmethod
    async def finalize_meeting(
        meeting_id: str,
        db: Session
    ) -> None:
        """
        백그라운드에서 호출되어 회의를 최종 완료 상태로 변경.
        """
        try:
            logger.info(f"Finalizing meeting: {meeting_id}")

            meeting = db.query(Meeting).filter(
                Meeting.meeting_id == meeting_id
            ).first()

            if not meeting:
                logger.error(f"Meeting not found for finalization: {meeting_id}")
                return

            if meeting.status != "ending":
                logger.warning(f"Meeting not in 'ending' status: {meeting.status}")
                return

            # 최종 상태로 변경
            end_dt = get_current_datetime()
            end_time_iso = format_datetime(end_dt, "%Y-%m-%dT%H:%M:%S%z")

            meeting.status = "completed"
            meeting.updated_at = end_time_iso

            db.commit()

            logger.info(f"Meeting finalized: {meeting_id}")

        except Exception as e:
            logger.error(f"Failed to finalize meeting: {e}", exc_info=True)
            db.rollback()
