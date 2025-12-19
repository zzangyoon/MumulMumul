from typing import List, Any, Literal

from pydantic import BaseModel, Field
from app.core.models import openai_chat_model
from app.core.schemas import AttendanceType
from app.services.attendance.schemas import AttendanceReport
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser

from typing import Literal
from pydantic import BaseModel, Field

class AttendanceInsight(BaseModel):
    """
    출결 로그 기반 LLM 인사이트 결과
    - 판정/집계 결과를 바꾸지 않음
    - 운영진 판단 및 커뮤니케이션 보조 용도
    """
    user_id: int = Field(
        description="학생 고유 ID"
    )
    risk_level: Literal[
        "고위험",
        "위험",
        "주의",
        "정상",
        "미확인",
    ] = Field(
        description="학생의 출결 위험 수준",
        default="미확인"
    )

    pattern_type: Literal[
        "안정형",
        "지각형",
        "조퇴형",
        "결석형",
        "불규칙형",
        "공백위험형",
        "신규",
        "데이터없음",
    ] = Field(
        description="학생의 주요 출결 패턴 유형",
        default="데이터없음"
    )

    trend: float = Field(
        description=(
            "최근 출결 추세 변화 값. "
            "양수는 개선(+), 음수는 악화(-), 0에 가까울수록 변화 없음. "
            "예: -0.25, 0.1"
        )
    )

    ops_action: str = Field(
        description="운영진이 취해야 할 권장 조치 또는 커뮤니케이션 가이드"
    )


class AttendanceInsightOutput(BaseModel):
    attendance_insights: List[AttendanceInsight] = Field(
        description="학생별 출결 인사이트 리스트"
    )

system_prompt = """
    너는 부트캠프 출결 분석 전문가이자 운영진 어드바이저다.
    출결 통계 데이터를 분석하여, 각 학생의 출결 위험 수준과 패턴을 평가하고,
    운영진이 취해야 할 조치 및 커뮤니케이션 가이드를 제안한다.
    추가로, 학생의 성향 정보도 참고한다

    - JSON 형식으로 출력한다.

    [성향 분석 정보]
    {tendency_context}

    [출력 형식]
    {format_instructions}

    [출결 규칙]
    {attendance_rules}
    """

parser = PydanticOutputParser(pydantic_object=AttendanceInsightOutput)

def generate_attendance_insights(
    report: AttendanceReport,
    tendency_context: str,
    attendance_rules: str,
) -> AttendanceReport:
    """
    배치 사이즈 10명으로
    1) AttendanceReport의 students 각 항목에 대해
        risk_level, pattern_type, trend, ops_action 필드 채우기
    2) report.summary의 high_risk_count, warning_count 갱신
    3) 완성된 AttendanceReport 반환
    """
    format_instructions = parser.get_format_instructions()

    
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", """
            아래 입력에는 여러 학생의 출결 데이터가 포함되어 있다.

            규칙:
            1) 입력에 등장하는 학생 수만큼 attendance_insights를 반드시 생성한다.
            2) 각 아이템에는 반드시 user_id 포함한다.
            3) 학생별 수치/요약을 근거로 서로 다른 판단을 하라. (복사/반복 금지)
            4) 출력은 JSON만.

            [출결 데이터]
            {attendance_data}
        """),
    ])
    llm = openai_chat_model()

    llm_chain = prompt | llm | parser

    # 배치 사이즈 10명 학생별로 LLM 호출
    batch_size = 10
    for i in range(0, len(report.students_stat), batch_size):
        batch_students = report.students_stat[i : i + batch_size]
        # 배치 학생들을 위한 context 생성

        attendance_context_list = [
            f"""
            [학생 ID: {student.user_id}, 이름: {student.name}]
            출석률: {student.attendance_rate:.2%}
            결석 횟수: {student.absent_count}
            지각 횟수: {student.late_count}
            조퇴 횟수: {student.early_leave_count}
            성향 유형: {student.personality_type}
            날짜별 출결 유형 요약: {student.attendance_records}
            최근 30일 출결 요약: {student.recent_30_attendance_summary}
            연속 결석 일수: {student.consecutive_absent_days}
            연속 지각 일수: {student.consecutive_late_days}
            최근 7일 출석률: {student.attendance_rate_7d:.2%}
            최근 14일 출석률: {student.attendance_rate_14d:.2%}
            최근 30일 출석률: {student.attendance_rate_30d:.2%}
            """ for student in batch_students]
        

        attendance_data = "\n======================================================\n".join(attendance_context_list)
        print(attendance_data)
        insights: AttendanceInsightOutput = llm_chain.invoke({
            "tendency_context":tendency_context, 
            "format_instructions":format_instructions,
            "attendance_data": attendance_data,
            "attendance_rules": attendance_rules
        })

        # 배치 학생 통계에 인사이트 반영
        insight_map = {x.user_id: x for x in insights.attendance_insights}

        for student_stat in batch_students:
            ins = insight_map.get(student_stat.user_id)
            if not ins:
                continue
            student_stat.risk_level = ins.risk_level
            student_stat.pattern_type = ins.pattern_type
            student_stat.trend = ins.trend
            student_stat.ops_action = ins.ops_action

    # summary의 고위험/위험 학생 수 갱신
    high_risk_count = sum(1 for s in report.students_stat if s.risk_level in ["고위험", "위험"])
    warning_count = sum(1 for s in report.students_stat if s.risk_level == "주의")
    report.summary.high_risk_count = high_risk_count
    report.summary.warning_count = warning_count

    return report