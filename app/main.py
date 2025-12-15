# uvicorn app.main:app --reload --host 0.0.0.0 --port 8020
from __future__ import annotations
from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.api.connection import router as connection_router
from app.api.attendance import router as attendance_router
from app.api.meeting import router as meeting_router
from app.api.team_chat import router as team_chat_router
from app.core.schemas import init_db
from app.core.db import engine
from app.core import schemas
from app.config import settings
from app.services.meeting.audio_processor import AudioProcessor
from app.services.meeting.audio_denoiser import AudioDenoiser
from app.services.meeting.embedding_service import EmbeddingService
from app.api.curriculum import router as curriculum_router
from app.api.user import router as user_router
from app.api.learning_chatbot import router as learning_chatbot_router
from app.api.meeting_chatbot import router as meeting_chatbot_router
from app.api.learning_quiz import router as learning_quiz_router
from app.api.feedbackBoard import router as feedback_router
from app.api.camp import router as camp_router
from app.core.mongodb import init_mongo, get_mongo_db
from app.core.schemas import init_db
from app.config import SQLITE_URL


# ------------------------------
# FastAPI 앱 생성
# ------------------------------
def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            print("DB 마이그레이션 적용")
            init_db(SQLITE_URL)
            init_mongo(get_mongo_db())
        except Exception:
            print("DB 마이그레이션 실패")

        # whisper 모델 : 앱 시작시 1회 로드
        print("Initializing Whisper model...")
        AudioProcessor.initialize_whisper(
            # max_workers = settings.MAX_WORKERS,
            model_size = settings.WHISPER_MODEL
        )
        print("Whisper model ready!")

        # AudioDenoiser 초기화
        print("AudioDenoiser 초기화 중...")
        AudioDenoiser.initialize()
        print("AudioDenoiser 초기화 완료")

        # Embedding 모델 초기화
        EmbeddingService.get_instance()
        print("All services initialized")
        
        yield

        AudioProcessor.shutdown()
        AudioDenoiser.shutdown()
        print("Application Shutdown Complete")

    app = FastAPI(title="Mumul Mumul Api", version="0.1.0", lifespan=lifespan)

    return app

app = create_app()

# ------------------------------
# 라우터 등록
# ------------------------------
app.include_router(connection_router, prefix="/connection")
app.include_router(attendance_router, prefix="/attendance")
app.include_router(meeting_router, prefix="/meeting")
app.include_router(curriculum_router, prefix="/curriculum")
app.include_router(user_router, prefix="/user")
app.include_router(learning_chatbot_router, prefix="/learning_chatbot")
app.include_router(meeting_chatbot_router, prefix="/meeting_chatbot")
app.include_router(team_chat_router, prefix="/chat")
app.include_router(learning_quiz_router, prefix="/learning_quiz")
app.include_router(feedback_router, prefix="/feedback")
app.include_router(camp_router, prefix="/camps")
