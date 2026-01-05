import sys
from pathlib import Path

# 이 파일 기준으로 프로젝트 루트 계산
CURRENT_FILE = Path(__file__).resolve()
ROOT_DIR = CURRENT_FILE.parents[4]   # .../MumulMumul
sys.path.append(str(ROOT_DIR))

from datetime import datetime
from pydantic import Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser

from app.core.models import openai_chat_model
from app.services.send_dispatch.schemas import MessagingAgentState, ParsedMessagingRequest

def build_parse_request_chain(llm):
    parser = PydanticOutputParser(pydantic_object=ParsedMessagingRequest)

    prompt = ChatPromptTemplate.from_messages([
        ("system",
         "너는 부트캠프 운영 메신저 에이전트의 요청 파서다. "
         "사용자 요청에서 캠프명, 전송할 사용자 이름, 메세지의 주제를 추출해라. "
         "출력은 반드시 지정된 JSON 스키마를 따라야 한다.\n"
         "{format_instructions}"
        ),
        ("human",
         """
            요청: {request_text}
            현재시간: {current_time}

            [목표]
            - 사용자의 요청을 'ParsedMessagingRequest' 스키마로 구조화한다.
            - 필요 시 DB 조회 계획(query_plans)을 함께 생성한다. (DB 조회가 불필요하면 query_plans는 빈 리스트로 둔다)

            [규칙]
            - target_scope는 'camp_all', 'user_list' 중 하나로 설정해야 한다.
               - camp_all: 캠프 전체에 메세지를 보낼 때
               - user_list: 특정 사용자들에게 메세지를 보낼 때
            - message_type는 'notice' 또는 'dm'으로 설정해야 한다.
               - notice: 공지 메세지일 때
               - dm: 개인 다이렉트 메세지일 때
            - camp_name은 'OO 캠프/OO 캠프로/OO 캠프에'에서 OO만 추출한다.
               - 예: "머물머물 캠프" → camp_name="머물머물"
            - user_names는 요청 텍스트에서 "직접적으로 언급된" 수신 대상 사용자 이름 리스트만 넣는다.
            - topic은 메세지의 핵심 주제만 짧게 요약한다. (예: 'QR 코드 출결')
               - 불명확하면 원문에서 가장 핵심 명사구를 topic으로 추출한다.
            - urgency는 'normal' 또는 'high'로 설정한다.
            - delivery_channel은 기본값 'websocket'을 사용한다.
            - language는 기본값 'ko'를 사용한다.

            DB 조회 계획(query_plans) 생성 규칙:
            - query_plans는 "메세지 작성 또는 대상 선정"을 위해 DB 조회가 필요할 때만 생성한다.
            - 다음 중 하나라도 해당하면 DB 조회를 고려한다:
               1) target_scope가 camp_all인데, 실제 발송을 위해 user_id 목록이 필요할 가능성이 높을 때
               2) user_names만 있고 user_id가 없어서 user_id 매핑이 필요할 때
               3) '지각/결석/출석률/출석 확인/미출석/활동 시간/접속 여부' 등 출결 상태에 따라 대상이 달라질 때
               4) '성향 맞춤' 개인화 문구 생성에 tendency_type_code 같은 데이터가 필요할 때
            - DB 조회가 필요하지 않다면 query_plans=[] 로 둔다.
            - query_plans를 생성할 때는 아래 DB_CATALOG에 존재하는 테이블/필드만 사용해야 한다.
            - 절대 password_hash 같은 민감 정보를 조회 대상으로 넣지 않는다.

            DB_CATALOG (허용 테이블/필드/조인 힌트):
            1) user_type (UserType)
            - fields: [type_id, type_name, permissions]
            2) user (User)
            - fields: [user_id, login_id, name, email, user_type_id, camp_id, tendency_completed, tendency_type_code, created_at]
            - forbidden_fields: [password_hash]
            3) camp (Camp)
            - fields: [camp_id, name, start_date, end_date, total_weeks]
            4) session_activity_log (SessionActivityLog)
            - fields: [id, camp_id, user_id, date, join_at, leave_at]
            5) attendance_daily (AttendanceDaily)
            - fields: [id, camp_id, user_id, date, is_finalized, attendance_type, total_active_time, first_join, last_leave, never_joined, created_at, updated_at]
            - attendance_type values: [ON_TIME, LATE, EARLY_LEAVE, ABSENT, UNNORMAL_ACTIVITY, UNKNOWN]

            Join hints:
            - user.camp_id -> camp.camp_id
            - user.user_type_id -> user_type.type_id
            - attendance_daily.user_id -> user.user_id
            - attendance_daily.camp_id -> camp.camp_id
            - session_activity_log.user_id -> user.user_id
            - session_activity_log.camp_id -> camp.camp_id

            query_plans 작성 규칙(중요):
            - query_plans는 "단계적 실행"이 가능하도록 순서를 고려해 작성한다.
            - 예: (1) camp_name -> camp_id 조회  (2) camp_id -> user_id 조회
            - 필터(filters)는 아래 연산자만 사용한다: eq, in, lt, lte, gt, gte, between
            - 날짜 '오늘'이 필요하면 value에 "TODAY" 문자열을 사용한다. (실제 날짜 변환은 서버에서 처리)
            - 이전 단계 결과를 참조해야 하면 다음 토큰을 사용한다:
            - "$camp_id" : 캠프 조회 결과로 얻은 camp_id
            - "$target_user_ids" : 타겟팅 단계에서 얻은 user_id 리스트
            - fields는 "최소 필드만" 조회하도록 작성한다. (메세지 작성/타겟팅에 필요한 컬럼만)
            - limit는 기본 200을 넘기지 않는다.

            출력 형식:
            - 반드시 ParsedMessagingRequest(JSON)만 출력한다. 설명 문장/주석/코드블럭 밖 텍스트를 덧붙이지 말 것.
            - query_plans가 없으면 빈 배열 [] 로 출력한다.
            """
        ),
    ]).partial(format_instructions=parser.get_format_instructions())

    # prompt | llm | parser
    return prompt | llm | parser

def parse_request_node(state: MessagingAgentState) -> MessagingAgentState:
    print("\n==============================")
    print("[NODE] parse_request_node START")
    print("[STATE] request_text =", state.request_text)
    print("[STATE] current_time =", state.current_time)
    print("==============================")

    try:
        llm = openai_chat_model()
        chain = build_parse_request_chain(llm)

        print("[LLM] parse_request_node invoke")
        parsed: ParsedMessagingRequest = chain.invoke({
            "request_text": state.request_text,
            "current_time": state.current_time.isoformat(),
        })

        print("[LLM] parse_request_node output")
        print(parsed.model_dump())

        state.parsed = parsed
        state.error = None

        print("[NODE] parse_request_node END")
        return state

    except Exception as e:
        print("[ERROR] parse_request_node failed")
        print(e)
        state.error = f"parse_request_node failed: {e}"
        return state

if __name__ == "__main__":
    request_text_1 = """
        머물머물 캠프로 긴급 공지를 보내고 싶어.
        내용은 훈련장려금(5차) 확인에 대한 안내야.

        확인해야하는 링크는:https://docs.google.com/spreadsheets/d/1vIETPD5mYXOT7mYD48xgZLlPJU7evHJid0eg_l3iHfI/edit?gid=1057320557#gid=1057320557
        단위 기간: 2025.11.07 ~ 2025.12.06
        근태일수 및 개별 고용형태에 따라 훈련장려금이 자동 산정되어 지급
        추가 확인이 필요한 사항은 월요일 오후 2시 <비고> 란에 기재해야함
        수령 시점: 26년 1월 초 예상
        """
    request_text_2 = """
        안녕, 머물머물 캠프의 모든 지각자들에게 QR코드 알림에 대한 DM을 보내줘.
        """
    request_text_3 = """
        머물머물 캠프의 사용자 김철수, 이영희, 박민수에게 '프로젝트 제출 마감'에 대한 메세지를 전달해줘.
        """
    
    test_state = MessagingAgentState(
        request_text=request_text_2,
        current_time=datetime.now()
    )

    result_state = parse_request_node(test_state)
    print(result_state.request_text)
    print("Parsed Result:", result_state.parsed)
    print("Error:", result_state.error)
