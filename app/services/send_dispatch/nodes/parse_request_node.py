import sys
from pathlib import Path

# 이 파일 기준으로 프로젝트 루트 계산
CURRENT_FILE = Path(__file__).resolve()
ROOT_DIR = CURRENT_FILE.parents[4]   # .../MumulMumul
sys.path.append(str(ROOT_DIR))

from datetime import datetime
from typing import Any, Dict, List

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser

from app.core.models import openai_chat_model
from app.services.send_dispatch.schemas import MessagingAgentState, ParsedMessagingRequest


# ----------------------------
# Post-process helpers (중요)
# ----------------------------
def _normalize_text(v: str) -> str:
    """camp_name 깨짐(머물머 물) 방어: 공백 제거 + strip"""
    return v.strip().replace(" ", "")


def _ensure_camp_name_normalized(parsed: ParsedMessagingRequest) -> ParsedMessagingRequest:
    """camp_name을 항상 정규화된 형태로 보정"""
    if getattr(parsed, "camp_name", None):
        parsed.camp_name = _normalize_text(str(parsed.camp_name).replace("캠프", ""))
    return parsed


def _ensure_late_dm_plans_default_today(parsed: ParsedMessagingRequest) -> ParsedMessagingRequest:
    """
    지각자 DM인데 날짜 필터가 빠진 경우 TODAY를 자동으로 추가.
    - attendance_daily plan에서 (attendance_type == LATE) 필터가 있으면 date 필터를 강제
    """
    plans = getattr(parsed, "query_plans", None) or []
    if not plans:
        return parsed

    new_plans = []
    for p in plans:
        plan = p.model_dump() if hasattr(p, "model_dump") else dict(p)
        table = plan.get("table") or plan.get("db_table")
        if table != "attendance_daily":
            new_plans.append(p)
            continue

        filters = plan.get("filters", []) or []
        # filters 내부도 혹시 몰라 정규화
        norm_filters: List[Dict[str, Any]] = []
        has_attendance_late = False
        has_date = False

        for f in filters:
            f_dict = f.model_dump() if hasattr(f, "model_dump") else dict(f)
            field = f_dict.get("field")
            op = f_dict.get("op")
            value = f_dict.get("value")

            if isinstance(value, str):
                value = value.strip()

            if field == "attendance_type" and op == "eq" and value == "LATE":
                has_attendance_late = True

            if field == "date":
                has_date = True

            f_dict["value"] = value
            norm_filters.append(f_dict)

        # ✅ 지각자 타겟팅이면 date 없을 때 TODAY 기본 적용
        if has_attendance_late and not has_date:
            norm_filters.append({"field": "date", "op": "eq", "value": "TODAY"})

        # 원본 pydantic plan 객체를 직접 수정 (가능한 경우)
        try:
            p.filters = norm_filters  # type: ignore
        except Exception:
            # plan이 dict 기반일 때를 대비(대부분 pydantic이라 여기 안 옴)
            plan["filters"] = norm_filters

        new_plans.append(p)

    parsed.query_plans = new_plans
    return parsed


def _ensure_camp_plan_name_filter_uses_parsed_camp_name(parsed: ParsedMessagingRequest) -> ParsedMessagingRequest:
    """
    LLM이 camp plan에서 value를 '머물머 물'처럼 깨뜨려도,
    state.parsed.camp_name(정규화된 값)을 camp.name eq 필터 value로 강제 보정.
    """
    if not getattr(parsed, "query_plans", None):
        return parsed
    if not getattr(parsed, "camp_name", None):
        return parsed

    camp_name = _normalize_text(str(parsed.camp_name))

    for p in parsed.query_plans:
        try:
            table = getattr(p, "table", None) or getattr(p, "db_table", None)
        except Exception:
            table = None

        # dict plan 케이스
        if table is None and isinstance(p, dict):
            table = p.get("table") or p.get("db_table")

        if table != "camp":
            continue

        # filters 접근
        filters = getattr(p, "filters", None)
        if filters is None and isinstance(p, dict):
            filters = p.get("filters", [])
        if not filters:
            continue

        new_filters = []
        for f in filters:
            f_dict = f.model_dump() if hasattr(f, "model_dump") else (dict(f) if isinstance(f, dict) else {})
            if f_dict.get("field") == "name" and f_dict.get("op") == "eq":
                f_dict["value"] = camp_name  # ✅ 강제
            else:
                # 문자열은 공백 제거 정도만
                if isinstance(f_dict.get("value"), str):
                    f_dict["value"] = _normalize_text(f_dict["value"])
            new_filters.append(f_dict)

        try:
            p.filters = new_filters  # type: ignore
        except Exception:
            if isinstance(p, dict):
                p["filters"] = new_filters

    return parsed


def _post_process_parsed(parsed: ParsedMessagingRequest) -> ParsedMessagingRequest:
    """
    운영 안정성을 위한 후처리:
    1) camp_name 정규화
    2) camp 조회 plan의 name 필터 value를 parsed.camp_name으로 강제
    3) 지각자(DM) 타겟팅에서 날짜 없으면 TODAY 기본 주입
    """
    parsed = _ensure_camp_name_normalized(parsed)
    parsed = _ensure_camp_plan_name_filter_uses_parsed_camp_name(parsed)
    parsed = _ensure_late_dm_plans_default_today(parsed)
    return parsed


# ----------------------------
# Chain builder
# ----------------------------
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

- camp_name 추출 규칙 (매우 중요)
  1) 'OO 캠프/OO 캠프로/OO 캠프에/OO캠프'에서 OO만 추출한다.
  2) camp_name에서 "캠프" 단어가 섞여 있으면 제거한다.
  3) camp_name은 반드시 정규화한다:
     - 좌우 공백 제거(strip)
     - 내부 공백 제거(replace(" ", ""))
     - 예: "머물머 물" 같이 끊겨 나오면 "머물머물"로 만들어라.
  4) 최종 camp_name 필드는 정규화된 값만 넣어라.

- user_names는 요청 텍스트에서 "직접적으로 언급된" 수신 대상 사용자 이름 리스트만 넣는다.
  - 없으면 null 또는 빈 리스트로 둔다(스키마 정의에 맞춤).

- topic은 메세지의 핵심 주제만 짧게 요약한다. (예: 'QR코드 알림', '프로젝트 제출 마감')

- urgency는 'normal' 또는 'high'
- delivery_channel 기본값 'websocket'
- language 기본값 'ko'

DB 조회 계획(query_plans) 생성 규칙:
- query_plans는 DB 조회가 필요할 때만 생성한다.
- 출결 상태(지각/결석/미출석/출석 등)에 따라 대상이 달라지면 DB 조회를 생성해야 한다.

query_plans 작성 규칙(중요):
- table 키만 사용한다. "db_table" 금지.
- filters는 항상 리스트이며, 각 원소는 {{field, op, value}} 형태다.
- 날짜가 필요하면 value="TODAY" 문자열을 사용한다.
- 이전 단계 결과 토큰: "$camp_id", "$target_user_ids"

✅ 출결/상태 기반 타겟팅 날짜 기본값(강제)
- '지각/지각자/결석/미출석/출석' 등 출결 상태 조건이 포함되어 있고 날짜를 명시하지 않았다면,
  attendance_daily 쿼리에 {{"field":"date","op":"eq","value":"TODAY"}} 를 반드시 포함한다.

✅ 지각자 DM 템플릿 규칙 (강제)
- 요청에 '지각자' 또는 '지각한'이 포함되고 message_type이 dm인 경우,
  query_plans는 반드시 아래 2단계로 생성한다:
  1) camp에서 camp_id 조회:
     - table="camp"
     - fields=["camp_id"]
     - filters=[{{"field":"name","op":"eq","value":"<정규화된 camp_name>"}}]
     - limit=1
     - save_as="camp_id"
  2) attendance_daily에서 오늘 지각한 user_id 조회:
     - table="attendance_daily"
     - fields=["user_id"]
     - filters=[
         {{"field":"camp_id","op":"eq","value":"$camp_id"}},
         {{"field":"attendance_type","op":"eq","value":"LATE"}},
         {{"field":"date","op":"eq","value":"TODAY"}}
       ]
     - limit=200
     - save_as="target_user_ids"
  3) attendance_daily에서 정상 출결 user_id 조회:
     - table="attendance_daily"
     - fields=["user_id"]
     - filters=[
         {{"field":"camp_id","op":"eq","value":"$camp_id"}},
         {{"field":"attendance_type","op":"eq","value":"ON_TIME"}},
         {{"field":"date","op":"eq","value":"TODAY"}}
       ]
     - limit=200
     - save_as="target_user_ids"

출력 형식:
- 반드시 ParsedMessagingRequest(JSON)만 출력한다. (설명/추가 텍스트 금지)
- query_plans가 없으면 [] 로 출력한다.
         """
        ),
    ]).partial(format_instructions=parser.get_format_instructions())

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

        # ✅ (추가) 운영 안정성을 위한 후처리 보정
        parsed = _post_process_parsed(parsed)

        print("[LLM] parse_request_node output (post-processed)")
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
    request_text_2 = "안녕, 머물머물 캠프의 모든 지각자들에게 QR코드 알림에 대한 DM을 보내줘."

    test_state = MessagingAgentState(
        request_text=request_text_2,
        current_time=datetime.now()
    )

    result_state = parse_request_node(test_state)
    print(result_state.request_text)
    print("Parsed Result:", result_state.parsed)
    print("Error:", result_state.error)
