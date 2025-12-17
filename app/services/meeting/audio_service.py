from fastapi import UploadFile, BackgroundTasks
from sqlalchemy.orm import Session
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict
from app.core.logger import setup_logger
from app.core.schemas import User, Meeting, MeetingParticipant, STTSegment
from app.services.meeting.audio_processor import AudioProcessor
from app.services.meeting.audio_denoiser import AudioDenoiser
from app.services.meeting.paths import PathManager
from app.services.meeting.schemas import AudioChunkUploadResponse
from app.services.meeting.meeting_service import MeetingService
from app.core.db import SessionLocal
from app.config import settings
from app.core.timezone import timestamp_to_datetime, get_current_datetime
import asyncio

logger = setup_logger(__name__)


class AudioService:
    """오디오 처리 서비스"""

    # 회의별 상태 추적
    _meeting_states: Dict[str, Dict] = {}

    CHUNK_TIMEOUT_SECONDS = 300
    GRACEFUL_SHUTDOWN_WAIT_SECONDS = 30
    
    def __init__(self):
        self.audio_processor = AudioProcessor()
        self.denoiser = AudioDenoiser.get_instance()
        # self.user_cumulative_times = {}


    def _init_meeting_state(self, meeting_id: str):
        """회의 상태 초기화"""
        if meeting_id not in self._meeting_states:
            self._meeting_states[meeting_id] = {
                "last_chunk_time": datetime.now(),
                "active_users": {},
                "processing_chunks": set(),
                "last_chunks_received": {}
            }
    
    def _update_last_chunk_time(self, meeting_id: str):
        """마지막 chunk 수신 시간 업데이트"""
        if meeting_id in self._meeting_states:
            self._meeting_states[meeting_id]["last_chunk_time"] = datetime.now()
    
    def _mark_chunk_processing(self, meeting_id: str, chunk_id: str):
        """처리 중인 chunk 추가"""
        if meeting_id in self._meeting_states:
            self._meeting_states[meeting_id]["processing_chunks"].add(chunk_id)
            logger.debug(
                f"  현재 처리 중인 chunks: "
                f"{len(self._meeting_states[meeting_id]['processing_chunks'])}개"
            )
    
    def _mark_chunk_completed(self, meeting_id: str, chunk_id: str):
        """처리 완료된 chunk 제거"""
        if meeting_id in self._meeting_states:
            self._meeting_states[meeting_id]["processing_chunks"].discard(chunk_id)
            logger.debug(
                f"  현재 처리 중인 chunks: "
                f"{len(self._meeting_states[meeting_id]['processing_chunks'])}개"
            )
    
    def _is_all_chunks_processed(self, meeting_id: str) -> bool:
        """모든 chunk 처리 완료 여부"""
        if meeting_id not in self._meeting_states:
            return True
        return len(self._meeting_states[meeting_id]["processing_chunks"]) == 0
    
    def _is_all_last_chunks_received(self, meeting_id: str) -> bool:
        """모든 사용자의 마지막 chunk 수신 완료 여부"""
        if meeting_id not in self._meeting_states:
            return True
        
        state = self._meeting_states[meeting_id]
        
        # 활성 사용자가 없으면 True
        if not state["active_users"]:
            return True
        
        # 모든 활성 사용자가 is_last=True를 보냈는지 확인
        for user_id in state["active_users"]:
            if not state["last_chunks_received"].get(user_id, False):
                return False
        
        return True
    
    async def check_timeout(self, meeting_id: str, db: Session) -> bool:
        """
        Timeout 체크 (5분 이상 chunk 없으면 자동 종료)
        
        Returns:
            True: timeout 발생, False: 정상
        """
        if meeting_id not in self._meeting_states:
            return False
        
        state = self._meeting_states[meeting_id]
        elapsed = (datetime.now() - state["last_chunk_time"]).total_seconds()
        
        if elapsed > self.CHUNK_TIMEOUT_SECONDS:
            logger.warning(
                f"  회의 {meeting_id} Timeout 발생!\n"
                f"   마지막 chunk: {elapsed:.0f}초 전\n"
                f"   자동 종료 처리..."
            )
            
            # 회의 강제 종료
            try:
                MeetingService.end_meeting(meeting_id, db)
                logger.info(f"✓ 회의 {meeting_id} 자동 종료 완료")
                return True
            except Exception as e:
                logger.error(f"자동 종료 실패: {e}")
                return False
        
        return False
    
    async def wait_for_processing(self, meeting_id: str) -> Dict:
        """
        회의 종료 전 처리 대기
        
        Returns:
            {
                "waited": bool,
                "wait_time_ms": int,
                "timed_out": bool
            }
        """
        logger.info(f"회의 {meeting_id} 처리 완료 대기 중...")
        
        start_time = datetime.now()
        max_wait_time = timedelta(seconds=self.GRACEFUL_SHUTDOWN_WAIT_SECONDS)
        
        # 1. 마지막 chunk 대기
        while not self._is_all_last_chunks_received(meeting_id):
            elapsed = datetime.now() - start_time
            if elapsed > max_wait_time:
                logger.warning(
                    f"  마지막 chunk 수신 대기 시간 초과 ({elapsed.total_seconds():.1f}초)"
                )
                break
            
            logger.debug(f"마지막 chunk 대기 중... ({elapsed.total_seconds():.1f}초)")
            await asyncio.sleep(1)
        
        # 2. 처리 중인 chunk 대기
        while not self._is_all_chunks_processed(meeting_id):
            elapsed = datetime.now() - start_time
            if elapsed > max_wait_time:
                logger.warning(
                    f"  chunk 처리 대기 시간 초과 ({elapsed.total_seconds():.1f}초)"
                )
                break
            
            processing_count = len(self._meeting_states[meeting_id]["processing_chunks"])
            logger.debug(
                f"처리 중인 chunk 대기 중... "
                f"({processing_count}개 남음, {elapsed.total_seconds():.1f}초)"
            )
            await asyncio.sleep(1)
        
        end_time = datetime.now()
        wait_time = end_time - start_time
        waited = wait_time.total_seconds() > 1
        timed_out = wait_time > max_wait_time
        
        logger.info(
            f" 처리 완료 대기 종료\n"
            f"   대기 시간: {wait_time.total_seconds():.1f}초\n"
            f"   Timeout 여부: {timed_out}"
        )
        
        return {
            "waited": waited,
            "wait_time_ms": int(wait_time.total_seconds() * 1000),
            "timed_out": timed_out
        }

    
    # 음성 청크 업로드 및 STT 처리
    async def upload_audio_chunk(
        self,
        meeting_id: str,
        audio_file: UploadFile,
        user_id: int,
        chunk_index: int,
        upload_timestamp: int,
        is_last: bool,
        background_tasks: BackgroundTasks,
        db: Session
    ) -> AudioChunkUploadResponse:
        
        logger.info(f"Audio chunk upload: Meeting={meeting_id}, User={user_id}, Chunk={chunk_index}")

        upload_dt = timestamp_to_datetime(upload_timestamp)
        server_dt = get_current_datetime()
        
        logger.info(
            f"타임스탬프 비교:\n"
            f"  upload_timestamp: {upload_timestamp}\n"
            f"  -> datetime: {upload_dt} (UTC 기준 변환)\n"
            f"  server_time: {server_dt} (UTC)\n"
            f"  차이: {(server_dt.timestamp() * 1000 - upload_timestamp)/1000:.1f}초"
        )
        
        # 회의 상태 초기화
        self._init_meeting_state(meeting_id)
        
        # 마지막 chunk 시간 업데이트
        self._update_last_chunk_time(meeting_id)
        
        # 활성 사용자 업데이트
        self._meeting_states[meeting_id]["active_users"][user_id] = chunk_index
        
        # 마지막 chunk 표시
        if is_last:
            self._meeting_states[meeting_id]["last_chunks_received"][user_id] = True
            logger.info(f"User {user_id}의 마지막 chunk 수신")
        
        # 1. 파일 읽기
        file_data = await audio_file.read()
        file_size_mb = len(file_data) / (1024 * 1024)
        logger.info(f"  File size: {file_size_mb:.2f} MB")
        
        # 2. 파일 검증
        validation = AudioProcessor.validate_audio_file(file_data)
        if not validation["is_valid"]:
            raise ValueError("Invalid audio format")
        
        # 3. 회의 정보 확인
        meeting = db.query(Meeting).filter(
            Meeting.meeting_id == meeting_id
        ).first()
        if not meeting:
            raise ValueError("Meeting not found")
        
        # 4. 사용자 확인
        user = db.query(User).filter(User.user_id == user_id).first()
        if not user:
            raise ValueError("User not found")
        
        # 5. 참가자 검증
        participant = (
            db.query(MeetingParticipant)
            .filter(
                MeetingParticipant.meeting_id == meeting_id,
                MeetingParticipant.user_id == user_id,
                MeetingParticipant.is_active == 1
            )
            .first()
        )
        if not participant:
            raise ValueError("User is not participating in this meeting")

        # 6. 파일 저장
        chunk_path = AudioProcessor.save_chunk_file(
            meeting_id, user_id, chunk_index, file_data
        )

        # 잡음 제거 (noisereduce)
        if settings.ENABLE_DENOISING and self.denoiser:
            try:
                denoised_path = self.denoiser.denoise_audio(chunk_path)
                logger.info(f"  잡음 제거 완료")
            except Exception as e:
                logger.warning(f"잡음 제거 실패, 원본 사용: {e}")
                denoised_path = chunk_path
        else:
            logger.debug(f"잡음 제거 비활성화 (원본 사용)")
            denoised_path = chunk_path

        # 7. 음성 파일 길이 측정
        audio_duration_ms = AudioProcessor.get_audio_duration_ms(denoised_path)
        logger.info(f"  음성 길이: {audio_duration_ms}ms ({audio_duration_ms/1000:.1f}초)")

        # 8. 녹음 시작 시점 계산
        chunk_start_timestamp = upload_timestamp - audio_duration_ms

        # 9. 회의 기준 상대 시간 계산
        chunk_relative_start_ms = chunk_start_timestamp - meeting.start_server_timestamp
        
        # 10. 이전 청크 경로 (겹침 처리용)
        chunk_dir = PathManager.get_user_chunk_dir(meeting_id, str(user_id))
        # prev_chunk_path = chunk_dir / f"chunk_{chunk_index - 1}.wav" if chunk_index > 0 else None
        prev_chunk_path = None
        if chunk_index > 0:
            prev_chunk_path = chunk_dir / f"chunk_{chunk_index - 1}.wav"
            if not prev_chunk_path.exists():
                prev_chunk_path = None

        # 11. chunk_id 생성 (처리 추적용)
        chunk_id = f"{meeting_id}_{user_id}_{chunk_index}"
        self._mark_chunk_processing(meeting_id, chunk_id)
        logger.info(f"Chunk {chunk_id} 처리 시작 표시 완료")

        # 누적 시간 가져오기
        # cumulative_time_ms = self._get_cumulative_time(meeting_id, user_id)
        
        # 12. 백그라운드 STT 처리
        background_tasks.add_task(
            self._process_stt_background,
            meeting_id = meeting_id,
            user_id = user_id,
            chunk_index = chunk_index,
            chunk_path = denoised_path,
            # chunk_path = chunk_path,
            prev_chunk_path = prev_chunk_path,
            speaker_name = user.name,
            chunk_relative_start_ms = chunk_relative_start_ms,
            chunk_id = chunk_id
        )
        
        return AudioChunkUploadResponse(
            meeting_id = meeting_id,
            user_id = user_id,
            chunk_index = chunk_index
        )
    
    # 백그라운드 STT 처리
    async def _process_stt_background(
        self,
        meeting_id: str,
        user_id: int,
        chunk_index: int,
        chunk_path: Path,
        prev_chunk_path: Path,
        speaker_name: str,
        chunk_relative_start_ms: int,
        chunk_id: str
    ):
        logger.info(f"[STT] User {user_id}, Chunk {chunk_index} started")
        db = SessionLocal()
        
        try:
            # 1. STT 처리
            stt_result = await self.audio_processor.transcribe_chunk_with_overlap(
                chunk_path = chunk_path,
                prev_chunk_path = prev_chunk_path,
                user_id = user_id,
                chunk_index = chunk_index,
                speaker_name = speaker_name,
                chunk_relative_start_ms = chunk_relative_start_ms
            )

            # # 2. 누적시간 업데이트
            # self._update_cumulative_time(
            #     meeting_id,
            #     user_id,
            #     stt_result["duration_ms"]
            # )

            # 2. 각 segment를 개별적으로 DB에 저장
            saved_count = 0
            skipped_count = 0

            for seg in stt_result["segments"]:
                # 후처리 : 빈 텍스트 제외
                if not seg["text"] or len(seg["text"]) < 2 :
                    logger.debug(f"빈 segment 건너뛰기 : {seg}")
                    skipped_count += 1
                    continue

                # 후처리 : 너무 짧은 segment 제외
                duration_ms = seg["end_time_ms"] - seg["start_time_ms"]
                if duration_ms < 500 :  # 0.5초 미만
                    logger.debug(f"짧은 segment 건너뛰기 ({duration_ms}ms) : {seg}")
                    skipped_count += 1
                    continue

                # segment_id 생성
                segment_id = (
                    f"seg_{meeting_id}_{user_id}_"
                    f"{chunk_index}_{seg['segment_index']}"
                )

                # confidence 조정
                text_length = len(seg["text"])
                adjusted_confidence = min(
                    0.95, 
                    seg["confidence"] + (text_length / 100) * 0.1
                )
            
                # DB 저장
                db_segment = STTSegment(
                    segment_id = segment_id,
                    meeting_id = meeting_id,
                    user_id = user_id,
                    chunk_index = chunk_index,
                    text = seg["text"].strip(),
                    confidence = adjusted_confidence,
                    start_time_ms = seg["start_time_ms"],
                    end_time_ms = seg["end_time_ms"],
                    source_chunks = stt_result["source_chunks"],
                    is_overlapped = stt_result["is_overlapped"]
                )
                db.add(db_segment)
                saved_count += 1

            db.commit()
            
            logger.info(
                f"[STT] User {user_id}, Chunk {chunk_index} 완료\n"
                f"   저장된 segments: {saved_count}"
            )

            self._mark_chunk_completed(meeting_id, chunk_id)
            logger.info(f"[STT] {chunk_id} 처리 완료 표시")
        
        except Exception as e:
            logger.error(f"[STT] Failed: {e}", exc_info=True)
            db.rollback()

            # 에러 발생해도 처리 완료 표시 (무한대기 방지)
            self._mark_chunk_completed(meeting_id, chunk_id)
            logger.warning(f"[STT] {chunk_id} 에러로 인한 처리 완료 표시")

        finally:
            db.close()