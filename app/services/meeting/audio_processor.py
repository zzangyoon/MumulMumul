import asyncio
import time
import io
import numpy as np
import soundfile as sf
from pathlib import Path
from typing import Dict, Optional
from app.core.logger import setup_logger
from faster_whisper import WhisperModel
from app.services.meeting.paths import PathManager

logger = setup_logger(__name__)


class AudioProcessor:
    
    whisper_model = None
    model_size = "large-v3"
    device = "cuda"
    compute_type = "float16"
    
    # Queue 방식
    stt_queue = None
    max_concurrent_stt = 2
    stt_semaphore = None
    
    CHUNK_DURATION_MS = 60000
    OVERLAP_SECONDS = 5.0
    
    @classmethod
    def initialize_whisper(cls, max_concurrent: int = 2, model_size: str = "large-v3"):
        """Whisper 모델 초기화 (앱 시작 시 한 번만)"""
        if cls.whisper_model is None:
            cls.model_size = model_size
            cls.max_concurrent_stt = max_concurrent
            
            logger.info("="*60)
            logger.info(f"Whisper 모델 초기화 (Queue 방식)")
            logger.info(f"  Model: {cls.model_size}")
            logger.info(f"  Device: {cls.device}")
            logger.info(f"  Compute Type: {cls.compute_type}")
            logger.info(f"  Max Concurrent: {cls.max_concurrent_stt}")
            logger.info("="*60)
            
            # 단일 모델 인스턴스 생성
            cls.whisper_model = WhisperModel(
                cls.model_size,
                device=cls.device,
                compute_type=cls.compute_type,
                num_workers=1
            )
            
            # Semaphore 생성 (동시 처리 제한)
            cls.stt_semaphore = asyncio.Semaphore(cls.max_concurrent_stt)
            
            logger.info(f"Whisper 모델 준비 완료")
    
    @classmethod
    def shutdown(cls):
        """종료 처리"""
        if cls.whisper_model:
            logger.info("Whisper 모델 종료 중...")
            cls.whisper_model = None
            logger.info("종료 완료")
    
    @staticmethod
    def save_chunk_file(
        meeting_id: str,
        user_id: int,
        chunk_index: int,
        file_data: bytes
    ) -> Path:
        """음성 청크 파일 저장"""
        try:
            chunk_dir = PathManager.get_user_chunk_dir(meeting_id, str(user_id))
            chunk_path = chunk_dir / f"chunk_{chunk_index}.wav"
            
            with open(chunk_path, 'wb') as f:
                f.write(file_data)
            
            file_size_kb = len(file_data) / 1024
            logger.info(
                f"Audio chunk 저장\n"
                f"   경로: {chunk_path}\n"
                f"   크기: {file_size_kb:.2f} KB"
            )
            
            return chunk_path
        
        except Exception as e:
            logger.error(f"Chunk 저장 실패: {e}")
            raise
    
    @staticmethod
    def validate_audio_file(file_data: bytes) -> Dict:
        """음성 파일 검증"""
        try:
            audio_buffer = io.BytesIO(file_data)
            data, sample_rate = sf.read(audio_buffer)
            
            if len(data.shape) == 1:
                channels = 1
            else:
                channels = data.shape[1]
            
            duration_ms = int((len(data) / sample_rate) * 1000)
            
            logger.info(
                f"Audio 검증 완료\n"
                f"   Duration: {duration_ms}ms\n"
                f"   Sample Rate: {sample_rate}Hz\n"
                f"   Channels: {channels}"
            )
            
            return {
                "is_valid": True,
                "duration_ms": duration_ms,
                "sample_rate": sample_rate,
                "channels": channels
            }
        
        except Exception as e:
            logger.error(f"Audio 검증 실패: {e}")
            return {
                "is_valid": False,
                "error": str(e)
            }
    
    @staticmethod
    def get_audio_duration_ms(audio_path: Path) -> int:
        """오디오 파일의 실제 길이 측정 (ms)"""
        try:
            data, sample_rate = sf.read(str(audio_path))
            duration_seconds = len(data) / sample_rate
            duration_ms = int(duration_seconds * 1000)
            return duration_ms
        except Exception as e:
            logger.error(f"Audio duration 측정 실패: {e}")
            return 60000
    
    @classmethod
    async def transcribe_chunk_with_overlap(
        cls,
        chunk_path: Path,
        prev_chunk_path: Optional[Path] = None,
        user_id: int = None,
        chunk_index: int = None,
        speaker_name: str = None,
        chunk_relative_start_ms: int = 0
    ) -> Dict:
        """
        Queue 기반 STT (비동기)
        """
        logger.info(
            f"STT 시작 (Queue 방식)\n"
            f"   User: {user_id}\n"
            f"   Chunk: {chunk_index}\n"
            f"   시작 시간: {chunk_relative_start_ms}ms (회의 기준)"
        )
        
        try:
            if not chunk_path.exists():
                raise FileNotFoundError(f"Audio 파일 없음: {chunk_path}")
            
            current_duration_ms = cls.get_audio_duration_ms(chunk_path)
            logger.info(f"현재 chunk duration: {current_duration_ms}ms")
            
            # ===== 1단계: 겹침 처리 =====
            source_chunks = [chunk_index]
            is_overlapped = False
            stt_audio_path = chunk_path
            overlap_offset_ms = 0
            
            if prev_chunk_path and prev_chunk_path.exists() and chunk_index > 0:
                logger.info("이전 chunk와 overlap 처리 중...")
                try:
                    prev_data, prev_sr = sf.read(str(prev_chunk_path))
                    curr_data, curr_sr = sf.read(str(chunk_path))

                    overlap_samples = int(cls.OVERLAP_SECONDS * prev_sr)

                    if len(prev_data) >= overlap_samples:
                        prev_overlap = prev_data[-overlap_samples:]
                        combined_audio = np.concatenate([prev_overlap, curr_data])

                        temp_path = chunk_path.parent / f"temp_combined_{chunk_path.name}"
                        sf.write(str(temp_path), combined_audio, curr_sr)
                    
                        stt_audio_path = temp_path
                        source_chunks = [chunk_index - 1, chunk_index]
                        is_overlapped = True
                        overlap_offset_ms = int(cls.OVERLAP_SECONDS * 1000)

                        logger.info(f"Overlap 적용 완료 (5초)")
                    else:
                        logger.warning(f"이전 chunk가 너무 짧아서 overlap 불가")
                
                except Exception as e:
                    logger.warning(f"Overlap 실패: {e}")
                    is_overlapped = False
            
            # ===== 2단계: STT 실행 (Semaphore로 제한) =====
            logger.info(f"[User {user_id}] STT 대기열 진입...")
            
            # Semaphore 획득 (동시 처리 제한)
            async with cls.stt_semaphore:
                logger.info(f"[User {user_id}] STT 시작")
                start_time = time.perf_counter()
                
                # asyncio.to_thread로 블로킹 함수를 비동기로 실행
                segments, info = await asyncio.to_thread(
                    cls._run_whisper_stt,
                    str(stt_audio_path)
                )
                
                elapsed = time.perf_counter() - start_time
                logger.info(f"[User {user_id}] STT 완료: {elapsed:.2f}s")
            
            # 임시 파일 삭제
            if is_overlapped and 'temp_path' in locals() and temp_path.exists():
                try:
                    temp_path.unlink()
                    logger.debug(f"임시 파일 삭제 완료")
                except Exception as e:
                    logger.warning(f"임시 파일 삭제 실패: {e}")
            
            # ===== 3단계: Segment 처리 =====
            if not segments:
                logger.warning(f"[User {user_id}] STT 결과 없음")
            
            logger.info(
                f"   STT 완료\n"
                f"      Segments: {len(segments)}\n"
                f"      Overlapped: {is_overlapped}\n"
                f"      처리 시간: {elapsed:.2f}s"
            )
            
            # ===== 4단계: 개별 segment 처리 =====
            processed_segments = []
            
            for idx, seg in enumerate(segments):
                seg_start_in_audio = seg["start"] * 1000
                seg_end_in_audio = seg["end"] * 1000
                
                # Overlap 고려
                if is_overlapped:
                    if seg_start_in_audio < overlap_offset_ms:
                        logger.debug(
                            f"Segment {idx}는 overlap 구간 내 → 건너뛰기"
                        )
                        continue
                    
                    actual_start_in_chunk = seg_start_in_audio - overlap_offset_ms
                    actual_end_in_chunk = seg_end_in_audio - overlap_offset_ms
                else:
                    actual_start_in_chunk = seg_start_in_audio
                    actual_end_in_chunk = seg_end_in_audio
                
                # 절대 시간 계산
                absolute_start_ms = chunk_relative_start_ms + actual_start_in_chunk
                absolute_end_ms = chunk_relative_start_ms + actual_end_in_chunk
                
                logger.debug(
                    f"Segment {idx}: "
                    f"회의내[{absolute_start_ms:.0f}-{absolute_end_ms:.0f}ms] "
                    f"'{seg['text'][:20]}...'"
                )
                
                processed_segments.append({
                    "text": seg["text"].strip(),
                    "confidence": seg["confidence"],
                    "start_time_ms": int(absolute_start_ms),
                    "end_time_ms": int(absolute_end_ms),
                    "segment_index": idx
                })
            
            logger.info(
                f"처리 완료: {len(processed_segments)} segments "
                f"(원본 {len(segments)}에서 필터링)"
            )
            
            return {
                "chunk_index": chunk_index,
                "user_id": user_id,
                "speaker_name": speaker_name,
                "segments": processed_segments,
                "duration_ms": current_duration_ms,
                "source_chunks": ",".join(map(str, source_chunks)),
                "is_overlapped": is_overlapped,
                "total_segments": len(processed_segments)
            }
        
        except Exception as e:
            logger.error(f"STT 실패: {e}", exc_info=True)
            raise
    
    @classmethod
    def _run_whisper_stt(cls, audio_path: str):
        """
        실제 Whisper STT 실행 (동기 함수)
        
        asyncio.to_thread로 호출됨
        """
        try:
            logger.debug(f"Whisper transcribe 시작: {audio_path}")
            
            # STT 수행
            segments_generator, info = cls.whisper_model.transcribe(
                audio_path,
                language="ko",
                beam_size=5,
                vad_filter=True,
                vad_parameters={
                    "threshold": 0.5,
                    "min_speech_duration_ms": 250,
                    "min_silence_duration_ms": 500,
                    "speech_pad_ms" : 300
                }
            )
            
            # Generator를 list로 변환 (점진적)
            segments = []
            for idx, segment in enumerate(segments_generator):
                duration = segment.end - segment.start

                if duration > 5.0:
                    logger.warning(
                        f"[긴 Segment 감지] {idx}번째\n"
                        f"  길이: {duration:.1f}초\n"
                        f"  시작: {segment.start:.1f}s\n"
                        f"  종료: {segment.end:.1f}s\n"
                        f"  텍스트: {segment.text[:100]}"
                    )
                segments.append({
                    "start": float(segment.start),
                    "end": float(segment.end),
                    "text": str(segment.text),
                    "confidence": float(segment.avg_logprob)
                })
                
                if (idx + 1) % 10 == 0:
                    logger.debug(f"  처리 중: {idx + 1} segments")
            
            logger.debug(f"Whisper transcribe 완료: {len(segments)} segments")
            
            return segments, info
        
        except Exception as e:
            logger.error(f"Whisper STT 에러: {e}", exc_info=True)
            raise