# config.py
import os
import pytz
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

load_dotenv()

SQLITE_URL = os.getenv("DB_URL", "sqlite:///storage/mumul.db")
MONGO_URL = "mongodb://localhost:27017"
MONGO_DB_NAME = "mumul"

DAILY_SCHEDULE = {
    "morning": {"start": 9, "end": 12},
    "afternoon": {"start": 13, "end": 18},
}

MEETING_CONFIG = {
    "min_active_seconds": 60,   # 1분 미만 참여는 무효 처리 등
}

class Settings(BaseSettings):

    model_config = SettingsConfigDict(
        extra="ignore",
        env_file=".env",
        case_sensitive=True,
        )
    # 앱 설정
    DEBUG: bool = True

    OPENAI_API_KEY: str | None = None
    
    # MongoDB
    MONGODB_URI: str = ""
    # MONGODB_URI: str = "mongodb://localhost:27017/"
    
    # 파일 저장소 (로컬)
    DATA_DIR: Path = Path("storage")
    MEETINGS_DIR: Path = DATA_DIR / "meetings"
    VECTORSTORE_DIR: Path = DATA_DIR / "vectorstore"
    
    # Whisper 설정
    WHISPER_MODEL: str = "large-v3"
    EMBEDDING_MODEL: str = "text-embedding-3-large"
    LLM_MODEL: str = "gpt-4o-mini"

    # 잡음 제거 설정
    ENABLE_DENOISING: bool = True

    # 프로세스 풀
    MAX_WORKERS: int = 2

    # Timezone
    TIMEZONE: pytz.BaseTzInfo = pytz.timezone("UTC")
    
    # class Config:
    #     env_file = ".env"
    #     case_sensitive = True
    
    def __init__(self, **data):
        super().__init__(**data)
        # 디렉토리 자동 생성
        for path in [self.DATA_DIR, self.MEETINGS_DIR, self.VECTORSTORE_DIR]:
            path.mkdir(parents=True, exist_ok=True)

settings = Settings()

CURRENT_FILE = Path(__file__).resolve()
ROOT_DIR = CURRENT_FILE.parents[1]
PERSONAL_SURVEY_CONFIG_PATH = ROOT_DIR / "storage/personal_survey.json"

WEEK_INDEX = 1 # 1주차