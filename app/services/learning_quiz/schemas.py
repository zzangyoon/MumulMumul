# app/services/learning_quiz/schemas.py

from pydantic import BaseModel
from typing import List

class QuizItem(BaseModel):
    id: int
    type: str
    question: str
    answer: str
    explanation: str


class QuizList(BaseModel):
    quiz: List[QuizItem]


class LearningQuizResponse(BaseModel):
    isLearningQuestion: bool
    grade: str
    quiz: List[QuizItem]


class LearningQuizRequest(BaseModel):
    userId: int
    grade: str


class ErrorDetail(BaseModel):
    errorCode: str
    message: str


class LearningQuizErrorResponse(BaseModel):
    isLearningQuestion: bool
    detail: ErrorDetail