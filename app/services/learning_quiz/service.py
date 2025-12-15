# app/services/learning_quiz/service.py

from app.services.learning_quiz.llm import generate_quiz
from app.services.learning_quiz.schemas import LearningQuizResponse, QuizItem
# from app.services.learning_quiz.vectorstore import search_context
# from app.services.learning_quiz.llm import check_learning_intent
from app.core.logger import setup_logger

logger = setup_logger(__name__)


def validate_grade(grade: str):
    valid_grades = ["초급", "중급", "고급"]
    if grade not in valid_grades:
        logger.error(f"[Invalid Grade] 입력된 grade 값: {grade}")
        raise ValueError("INVALID_GRADE")

# def get_context(question: str) -> str:
#     return search_context(question, k=3)

def create_quiz(context: str, grade: str) -> LearningQuizResponse:

    validate_grade(grade)
    
    # context 기반 퀴즈 생성
    quiz_list = generate_quiz(context, grade)

    return LearningQuizResponse(
        isLearningQuestion=True,
        grade=grade,
        quiz=quiz_list.quiz
    )
