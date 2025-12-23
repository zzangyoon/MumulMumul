# ------------------------------------------------------------
# 7) F. 공지 및 DM 자동화 레이어
#   - 여러 요청(예시 - 오늘 지각자들에게 DM 보내줘/학습 리포트를 기반으로 연습 문제 만들어서 보내줘/00캠프 학생들에게 00에 대한 공지 보내줘)을 기반으로
#   -> DM 대상자 선정
#   -> 메시지 생성 
#   -> dispatch 로그 저장
# ------------------------------------------------------------
import datetime
from typing import Any
from requests import Session

def plan_and_dispatch_dm(
    db: Session,
    request_data: Any,
    current_time: datetime.datetime
):
    """공지 및 DM 자동화 서비스"""
    # TODO: 구현 필요
    # 1) 요청 분석 및 대상자 선정
    # 2) 메시지 생성
    # 3) DM 발송 및 로그 저장

    return "Not implemented yet"
