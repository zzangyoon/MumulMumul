# app/services/learning_quiz/llm.py

import json
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.services.learning_quiz.schemas import QuizList
from app.services.learning_quiz.prompt import QUIZ_GENERATION_PROMPT
from app.core.logger import setup_logger

load_dotenv()
logger = setup_logger(__name__)

# 1) Parser (QuizList JSON 구조 강제)
quiz_parser = PydanticOutputParser(pydantic_object=QuizList)

# 2) Prompt (STEP 3에서 만든 Prompt 사용)
prompt = ChatPromptTemplate.from_template(QUIZ_GENERATION_PROMPT)

# 3) LLM 생성
llm = ChatOpenAI(
    model="gpt-4.1-mini",  # JSON 안정성 ↑
    temperature=0.1
)

# 4) Prompt + LLM + Parser 를 Chain으로 합치기
quiz_chain = prompt | llm | quiz_parser


# 5) 외부에서 실행하는 함수 (service에서 불러씀)
def generate_quiz(context: str, grade: str) -> QuizList:
    """
    실제로 퀴즈 5개를 생성하는 함수.
    vectorstore 검색 결과(context), 난이도(grade)를 조합하여
    JSON 구조의 퀴즈 리스트를 반환한다.
    """

    logger.info("[Quiz Generation] LLM 호출 시작")

    # parser가 사용할 format_instructions 가져오기
    format_instructions = quiz_parser.get_format_instructions()

    try:
        result = quiz_chain.invoke({
            "context": context,
            "grade": grade,
            "format_instructions": format_instructions
        })

        logger.info("[Quiz Generation] 성공적으로 JSON 파싱 완료")
        return result

    except Exception as e:
        logger.error(f"[Quiz Generation Error] {e}")
        raise e


# ========= 학습 질문 여부 판단용 Prompt =========

INTENT_PROMPT = ChatPromptTemplate.from_template("""
당신은 사용자의 질문이 '부트캠프 학습과 관련된 질문인지' 판단하는 AI입니다.

아래 질문이 학습 관련이면 "YES"
아니면 "NO"만 답변하세요.

질문:
{question}
""")

# Intent 판단용 LLM (짧은 응답이므로 작은 모델 가능)
intent_llm = ChatOpenAI(model="gpt-4.1-mini", temperature=0)

# Chain
intent_chain = INTENT_PROMPT | intent_llm


def check_learning_intent(question: str) -> bool:
    """
    LLM을 사용하여 학습 관련 질문인지 판단합니다.
    YES → True
    NO → False
    """

    try:
        result = intent_chain.invoke({"question": question})
        answer = result.content.strip().upper()

        return answer == "YES"

    except Exception as e:
        logger.error(f"[Intent Check Error] {e}")
        return False
