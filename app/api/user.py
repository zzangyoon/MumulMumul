# app/api/user_router.py

import sys

sys.path.append("../..")

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.schemas import User, UserType, SessionActivityLog
from app.core.db import get_db

router = APIRouter()


# ===========================
# Pydantic Schemas
# ===========================
class LoginRequest(BaseModel):
    loginId: str
    password: str


class LoginResponse(BaseModel):
    userId: int
    name: str
    campId: Optional[int] = None
    userType: str
    tendencyCompleted: bool
    tendencyTypeCode: Optional[str] = None

class LogoutRequest(BaseModel):
    userId: int

class SurveyResultRequest(BaseModel):
    # 성향 분석 문항 응답 저장
    userId: int
    result: list[int]

class SurveyResultResponse(BaseModel):
    userId: int
    typeCode: str


# ===========================
# API Endpoints
# ===========================

@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    """
    로그인 + 성향분석 완료 여부 반환
    SessionActivityLog 기록 추가
    """
    user: User | None = (
        db.query(User)
        .join(UserType)
        .filter(User.login_id == payload.loginId)
        .first()
    )

    if not user or not payload.password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "errorCode": "LOGIN_FAILED",
                "message": "아이디 또는 비밀번호가 잘못되었습니다.",
            },
        )
    
    # 세션 활동 로그 기록
    log = SessionActivityLog(
        user_id=user.user_id,
        join_at=datetime.utcnow()
    )
    db.add(log)
    db.commit()

    print(f"User {user.user_id} logged in at {log.join_at}")

    return LoginResponse(
        userId=user.user_id,
        name=user.name,
        userType=user.user_type.type_name,
        campId=user.camp_id,
        tendencyCompleted=bool(user.tendency_completed),
        tendencyTypeCode=user.tendency_type_code,
    )


@router.post("/logout")
def logout(payload: LogoutRequest, db: Session = Depends(get_db)):
    """
    로그아웃 처리 + SessionActivityLog 기록 업데이트
    """
    userId = payload.userId

    log: SessionActivityLog | None = (
        db.query(SessionActivityLog)
        .filter(SessionActivityLog.user_id == userId)
        .order_by(SessionActivityLog.join_at.desc())
        .first()
    )

    if log and not log.leave_at:
        log.leave_at = datetime.utcnow()
        db.commit()

    print(f"User {userId} logged out at {log.leave_at if log else 'N/A'}")

    return {"message": "로그아웃 처리 완료"}


import json
from pathlib import Path
from app.config import PERSONAL_SURVEY_CONFIG_PATH

def load_trait_config(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

priority_order = ["analyst", "pillar", "balancer", "supporter", "doer"]
def calculate_personality_type(result, config):
    questions = config["questions"]

    persona_scores = {
        "analyst": 0,
        "doer": 0,
        "balancer": 0,
        "supporter": 0,
        "pillar": 0,
    }

    # 1) 기본 점수 누적
    for i, user_choice in enumerate(result):
        question = questions[i]
        choice = question["choices"][user_choice]
        weights = choice.get("personaWeights", {})
        for persona, w in weights.items():
            if persona in persona_scores:
                persona_scores[persona] += w

    # 2) 타입별 보정 계수 적용 (analyst 너프, 나머지 살짝 버프)
    adjust_factors = {
        "analyst":   0.60,   # 분석가 살짝 너프
        "doer":      0.65,   # 실행가 살짝 버프
        "balancer":  0.67,   # 밸런서 약간 버프
        "supporter": 0.63,   # 협력가 약간 버프
        "pillar":    0.69    # 원칙주의자 버프
    }

    for persona, factor in adjust_factors.items():
        persona_scores[persona] *= factor

    max_score = max(persona_scores.values())
    candidates = [p for p, s in persona_scores.items() if s == max_score]

    for p in priority_order:
        if p in candidates:
            type_code = p
            break

    return type_code, persona_scores

@router.get("/survey", response_model=dict)
def get_survey_questions():
    """
    personal_survey.json 기반 성향 분석 문항 반환
    """
    personal_survey_config = load_trait_config(PERSONAL_SURVEY_CONFIG_PATH)
    return {
        "characters": personal_survey_config["characters"],
        "questions": personal_survey_config["questions"]
    }


@router.post("/survey-result", response_model=SurveyResultResponse)
def submit_survey_result(payload: SurveyResultRequest, db: Session = Depends(get_db)):
    """
    personal_survey.json 기반 성향 분석 결과 저장
    점수대별로 type_code 부여 (analyst, doer, balancer, supporter, pillar)
    """
    user = db.query(User).filter(User.user_id == payload.userId).first()

    personal_survey_config = load_trait_config(PERSONAL_SURVEY_CONFIG_PATH)

    result = payload.result

    if len(result) != len(personal_survey_config["questions"]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "errorCode": "INVALID_SURVEY_RESULT",
                "message": "설문 문항 수와 응답 수가 일치하지 않습니다.",
            }
        )

    type_code, score = calculate_personality_type(result, personal_survey_config)

    # user.tendency_completed = 1
    user.tendency_type_code = type_code
    db.commit()

    print(f"User: {user.user_id}, Type Code: {type_code} Score: {score}")

    return SurveyResultResponse(
        userId=user.user_id,
        typeCode=type_code,
    )

