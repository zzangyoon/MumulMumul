# app/api/learning_quiz.py
import sys
from pathlib import Path

from app.services.db_service.curriculum_config import get_curriculum_config_for_camp

CURRENT_FILE = Path(__file__).resolve()
ROOT_DIR = CURRENT_FILE.parents[2]   # .../MumulMumul
sys.path.append(str(ROOT_DIR))

from typing import Union
from fastapi import APIRouter, Depends, HTTPException
from requests import Session
from app.config import WEEK_INDEX
from app.core.db import get_db
from app.core.mongodb import CurriculumConfig, CurriculumReport
from app.services.db_service.camp import get_camp_by_user_id
from app.services.db_service.curriculum_reports import fetch_curriculum_report
from app.services.learning_quiz.service import create_quiz
from app.services.learning_quiz.schemas import LearningQuizRequest, LearningQuizResponse, LearningQuizErrorResponse
from app.core.logger import setup_logger
from streamlit_app.api.curriculum import create_curriculum_report

router = APIRouter()
logger = setup_logger(__name__)


@router.post(
    "/generate",
    response_model=Union[LearningQuizResponse, LearningQuizErrorResponse]
)
def create_learning_quiz(payload: LearningQuizRequest, db: Session = Depends(get_db)):
    """
    학습 퀴즈 생성 API
    - OX 퀴즈 5개 생성
    """

    grade = payload.grade
    user_id = payload.userId
    camp_id = 2 # get_camp_by_user_id(db, user_id).camp_id
    week_index = WEEK_INDEX

    try:
        context = ""

        curriculum_config: CurriculumConfig = get_curriculum_config_for_camp(camp_id)
        if curriculum_config:
            curriculum_config_week = curriculum_config.weeks[week_index - 1]
            context += "[이번주 커리큘럼]\n" + " ".join(curriculum_config_week.topics) + "\n"

        curriculum_report: CurriculumReport = fetch_curriculum_report(camp_id, week_index)
        if curriculum_report:
            context += "[학생들이 어려워하는 내용]\n" + curriculum_report['ai_insights']['hardest_part_summary']

        logger.info(f"[커리큘럼 리포트 기반 컨텍스트 획득] camp_id: {camp_id}, week_index: {week_index}")
        result = create_quiz(context, grade)
        logger.info(f"[학습 퀴즈 생성 성공] user_id: {user_id}, grade: {grade}, quiz_count: {len(result.quiz)}")
        return result

    except ValueError as e:

        # grade 잘못된 경우
        if str(e) == "INVALID_GRADE":
            raise HTTPException(
                status_code=400,
                detail={
                    "errorCode": "INVALID_REQUEST",
                    "message": "grade 값은 초급/중급/고급 중 하나여야 합니다."
                }
            )

        # 서버 오류
        else:
            raise HTTPException(status_code=500, detail="Internal Server Error")


if __name__ == "__main__":
    grade = "초급"
    user_id = 208
    db: Session = next(get_db())
    camp_id = get_camp_by_user_id(db, user_id).camp_id
    week_index = WEEK_INDEX

    curriculum_report: CurriculumReport = fetch_curriculum_report(camp_id, week_index)
    if not curriculum_report:
        curriculum_report: CurriculumReport = create_curriculum_report(camp_id, week_index)
    context = curriculum_report['ai_insights']['hardest_part_summary']
    result = create_quiz(context, grade)
    print(result)