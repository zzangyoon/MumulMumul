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
         "요청: {request_text}\n"
         "현재시간: {current_time}\n\n"
         "규칙:\n"
         "- target_scope는 'camp_all', 'user_list' 중 하나로 설정해야 한다.\n"
         "  - camp_all: 캠프 전체에 메세지를 보낼 때\n"
         "  - user_list: 특정 사용자들에게 메세지를 보낼 때\n"
         "- message_type는 'notice' 또는 'dm'으로 설정해야 한다.\n"
         "  - notice: 공지 메세지일 때\n"
         "  - dm: 개인 다이렉트 메세지일 때\n"
         "- camp_name은 'OO 캠프/OO 캠프로/OO 캠프에'에서 OO만 추출\n"
         "- user_names는 직접적으로 언급된 메세지를 받는 사용자 이름 리스트\n"
         "- topic은 메세지의 핵심 주제만 짧게 요약(예: 'QR 코드 출결')\n"
         "   - 불명확하면 topic은 원문에서 가장 핵심 명사구로 추출\n"
         "- urgency는 'normal' 또는 'high'로 설정\n"
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
        안녕, 머물머물 캠프에 있는 모든 사람들에게 'QR 코드 출결'에 대한 공지를 보내줘.
        """
    request_text_3 = """
        머물머물 캠프의 사용자 김철수, 이영희, 박민수에게 '프로젝트 제출 마감'에 대한 메세지를 전달해줘.
        """
    
    test_state = MessagingAgentState(
        request_text=request_text_3,
        current_time=datetime.now()
    )

    result_state = parse_request_node(test_state)
    print(result_state.request_text)
    print("Parsed Result:", result_state.parsed)
    print("Error:", result_state.error)
