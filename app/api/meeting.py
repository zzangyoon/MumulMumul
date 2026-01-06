from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from app.core.logger import setup_logger
from app.core.db import get_db
from app.services.meeting.schemas import AudioChunkUploadResponse, StartMeetingRequest, StartMeetingResponse, JoinMeetingRequest, JoinMeetingResponse, EndMeetingResponse
from app.services.meeting.audio_processor import AudioProcessor
from app.services.meeting.meeting_service import MeetingService
from app.services.meeting.audio_service import AudioService
from app.services.meeting.timeline_service import TimelineService
from app.services.meeting.pipeline_service import RAGPipelineService

logger = setup_logger(__name__)
router = APIRouter()

# service instance
meeting_service = MeetingService()
audio_service = AudioService()
audio_processor = AudioProcessor()
timeline_service = TimelineService()
pipeline_service = RAGPipelineService()

# 회의 시작
@router.post("/start", response_model = StartMeetingResponse)
async def start_meeting(
    request: StartMeetingRequest,
    db: Session = Depends(get_db)
):
    logger.info("Starting new meeting")
    try:
        return meeting_service.start_meeting(request, db)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to start meeting: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    

# 회의 참가
@router.post("/{meeting_id}/join", response_model = JoinMeetingResponse)
async def join_meeting(
    meeting_id: str,
    request: JoinMeetingRequest,
    db: Session = Depends(get_db)
):
    logger.info(f"User {request.user_id} joining meeting {meeting_id}")
    try:
        return meeting_service.join_meeting(meeting_id, request, db)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to join meeting: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 음성 청크 업로드
@router.post("/{meeting_id}/audio_chunk", response_model=AudioChunkUploadResponse)
async def upload_audio_chunk(
    meeting_id: str,
    audio_file: UploadFile = File(...),
    user_id: int = Form(...),
    chunk_index: int = Form(...),
    upload_timestamp: int = Form(...),
    is_last: bool = Form(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db)
):
    # 파일 이름과 content-type 확인
    logger.info(f"Received file: {audio_file.filename}")
    logger.info(f"Content type: {audio_file.content_type}")
    logger.info(f"upload_timestamp: {upload_timestamp}, is_last: {is_last}")

    try:
        return await audio_service.upload_audio_chunk(
            meeting_id=meeting_id,
            audio_file=audio_file,
            user_id=user_id,
            chunk_index=chunk_index,
            upload_timestamp=upload_timestamp,
            is_last=is_last,
            background_tasks=background_tasks,
            db=db
        )
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Audio upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 회의 종료
@router.post("/{meeting_id}/end", response_model=EndMeetingResponse)
async def end_meeting(
    meeting_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    try:
        # 1. Meeting 즉시 종료 처리
        result = await meeting_service.end_meeting(
            meeting_id = meeting_id,
            db = db
        )

        # 2. 나머지는 백그라운드 처리
        background_tasks.add_task(
            _finalize_meeting_background,
            meeting_id = meeting_id
        )

        return result

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"End meeting failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    

async def _finalize_meeting_background(meeting_id: str):
    """백그라운드에서 실행되는 회의 마무리 작업"""
    from app.core.db import SessionLocal
    db = SessionLocal()
    try:
        # 1. 오디오 처리 완료 대기
        await audio_service.wait_for_processing(meeting_id)
        
        # 2. 최종 종료 처리
        await meeting_service.finalize_meeting(meeting_id, db)
        
        # 3. RAG 파이프라인
        await pipeline_service.run_rag_pipeline(meeting_id = meeting_id)
    finally:
        db.close()
