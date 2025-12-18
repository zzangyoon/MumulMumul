# app/services/attendance/llm.py

import json
from typing import Dict, Any

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate


def build_ai_insights_chain(model_name: str = "gpt-4.1-mini"):
    """
    출결 통계(JSON)를 받아서 ai_insights (AIInsights 모델)를 생성하는 LangChain 체인
    """
    llm = ChatOpenAI(
        model=model_name,
        temperature=0.2,
    ).with_structured_output(AIInsights)

    system_prompt = """
        너는 온라인 부트캠프 운영진을 위한 출결 리포트를 작성하는 분석가임.
        말투는 **보고서형(~임/~함 체)**으로 통일하고,
        운영진이 바로 액션을 정할 수 있도록 핵심 요약과 실행 항목을 명확하게 작성함.

        입력으로 캠프의 출결 관련 요약 지표와 학생별 출석 패턴 정보가 주어짐.
        이를 바탕으로 아래 5개 필드를 채워야 함:

        1) summary_one_line
        - 이 반의 출석/참여 상황을 한 문장으로 요약
        - 예: "출석률은 안정적이나, 최근 일주일간 일부 학습자의 참여 감소가 뚜렷하게 나타남."

        2) attendance_summary
        - 지난 기간 동안의 출석률 흐름, 주차별 특징, 전반적인 참여 상태를 정리

        3) risk_signals_summary
        - 고위험/주의 학습자와 최근 7일 저활동 인원을 중심으로
            어떤 이탈 신호가 있는지 정리

        4) short_term_actions
        - 1~2주 안에 실행할 수 있는 구체적인 운영 액션
        - 반드시 불릿 리스트 형태로 작성 (각 항목은 한 줄)

        5) mid_term_actions
        - 3주~이후를 생각한 개선 방향, 구조적인 제안
        - 반드시 불릿 리스트 형태로 작성 (각 항목은 한 줄)

        가능하면 아래 정보를 적극 활용함:
        - summary_cards: 평균 출석률, 최근 7일 저접속 인원 수, 주의/고위험 인원 수
        - charts.attendance_timeseries: 주차별 출석률 흐름
        - tables.top_risk_students: 주요 위험 인원 (이름, 최근 7일 접속일수, 위험도)
        - tables.student_list: 전체 학생의 출석 패턴(위험도, pattern_type 등)
    """

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            (
                "human",
                "아래는 특정 캠프의 출결 통계 데이터임.\n\n"
                "출결 통계 JSON:\n{attendance_json}\n\n"
                "위 데이터를 바탕으로 AIInsights 스키마에 맞게 리포트를 작성하라.",
            ),
        ]
    )

    chain = prompt | llm
    return chain


def generate_ai_insights(attendance_struct: Dict[str, Any]) -> AIInsights:
    """
    build_attendance_structure()로 만든 dict를 받아
    LangChain 체인으로 AIInsights를 생성
    """
    chain = build_ai_insights_chain()
    attendance_json = json.dumps(attendance_struct, ensure_ascii=False)
    ai_insights: AIInsights = chain.invoke({"attendance_json": attendance_json})
    return ai_insights
