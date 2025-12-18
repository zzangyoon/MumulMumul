import os
import logging
from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_chroma import Chroma
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from operator import itemgetter

# ==============================================================
# 로깅 설정
# ==============================================================
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(asctime)s - %(message)s",
)
logger = logging.getLogger(__name__)

load_dotenv()


# ==============================================================
# 기본 설정
# ==============================================================

DB_PATH = r"C:\POTENUP\MumulMumul\storage\vectorstore\curriculum_all_new"
COLLECTION = "curriculum_all_new"

LLM_MODEL = "gpt-4o-mini"
EMBEDDING_MODEL = "text-embedding-3-large"

SEARCH_K = 3
FETCH_K = 8


# ==============================================================
# 수준별 답변 규칙
# ==============================================================

GRADE_RULES = {
    "초급": """
- 어려운 단어 사용 금지
- 전문 용어 등장 시 반드시 쉬운 말로 풀어서 먼저 설명
- 비유·예시 중심으로 설명
- 너무 긴 문장은 금지 (짧게 끊어서 설명)
""",
    "중급": """
- 개념의 핵심 정의를 정확하게 제공
- 필요 시 용어 사용 가능하나 불필요한 확장 금지
- 왜 이런 개념이 필요한지 1번 설명
- 실무에서 헷갈리는 포인트도 함께 제공
""",
    "고급": """
- 내부 동작 원리 중심으로 설명
- 구조, 메커니즘, 메모리·성능 등 심화 내용 포함 가능
- 필요한 경우 수식·전문 용어 사용 가능
- 다른 기술과 비교 설명 가능
"""
}

# ==============================================================
# 히스토리 포맷 함수
# ==============================================================
def format_history(history=[]):
    if len(history) > 10:
        history = history[-10:]
    return "\n".join([f"{msg.role}: {msg.content}" for msg in history])



# ==============================================================
# RAG 체인 초기화
# ==============================================================
def initialize_rag_chain():
    logger.info("🔧 initialize_rag_chain() 실행 시작")

    try:
        logger.info("1) 임베딩 모델 로딩 중...")
        embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL)

        logger.info("2) Chroma 벡터스토어 연결 시도...")
        vectorstore = Chroma(
            persist_directory=DB_PATH,
            embedding_function=embeddings,
            collection_name=COLLECTION,
        )

        logger.info("3) Retriever 구성 중...")
        retriever = vectorstore.as_retriever(
            search_type="mmr",
            search_kwargs={"k": SEARCH_K, "fetch_k": FETCH_K}
        )

        logger.info("4) 프롬프트 템플릿 설정 중...")
        template = """
        당신은 부트캠프 학생을 위한 학습 도우미 챗봇입니다.
        답변은 반드시 제공된 [Context] 안의 정보만 사용해야 합니다.
        문서에 없는 내용은 절대 지어내지 마세요.
        [History]는 이전 대화 내역입니다. 필요 시 참고하세요.
        [FORMAT] 형식에 맞게 답변하세요.

        [FORMAT]
        - 답변은 반드시 1문장만 사용
        - 필요한 경우 예시는 한 줄만 허용
        - 불릿 포인트 금지
        - 부가 설명, 실무 포인트 등 추가 정보 금지
        
        [학생 수준]
        {grade}

        [답변 규칙]
        {grade_rules}

        -------------------------
        [Context]
        {context}

        [Question]
        {question}
        -------------------------

        [History]
        {history}
        """

        prompt = ChatPromptTemplate.from_template(template)

        logger.info("5) LLM 모델 로딩 중...")
        model = ChatOpenAI(model=LLM_MODEL, temperature=0.2)

        logger.info("6) RAG 체인 최종 생성 완료")

        # history 포맷 함수인 체인에 추가 코드
        rag_chain = (
            {
                "context": itemgetter("question") | retriever,
                "question": itemgetter("question"),
                "grade": itemgetter("grade"),
                "grade_rules": itemgetter("grade_rules"),
                "history": lambda inputs: format_history(inputs.get("history", [])),
            }
            | prompt
            | model
            | StrOutputParser()
        )
        return rag_chain

    except Exception as e:
        logger.error(f"❌ initialize_rag_chain() 중 오류 발생: {e}")
        raise


# ==============================================================
# answer() 함수
# ==============================================================

rag_chain = initialize_rag_chain()

def answer(question, grade="중급", history=[]):
    logger.info(f"💬 answer() 호출됨 | question='{question}', grade='{grade}'")

    if grade not in GRADE_RULES:
        logger.error(f"❌ 잘못된 grade 입력됨: {grade}")
        raise ValueError("grade는 '초급', '중급', '고급' 중 하나여야 합니다.")

    try:
        logger.info("🔍 RAG 체인 초기화 중...")
        rag = rag_chain

        logger.info("🤖 RAG 체인 실행 중...")
        result = rag.invoke({
            "question": question,
            "grade": grade,
            "grade_rules": GRADE_RULES[grade],
            "history": history,
        })

        logger.info("✅ answer() 응답 생성 완료")
        return result

    except Exception as e:
        logger.error(f"❌ answer() 실행 중 오류 발생: {e}")
        return f"[오류 발생] {e}"

