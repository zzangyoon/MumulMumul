# app/services/learning_quiz/vectorstore.py

import os
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from app.core.logger import setup_logger

logger = setup_logger(__name__)

DB_PATH = "storage/vectorstore/curriculum_all_new"
COLLECTION = "curriculum_all_new"


def load_vectorstore():
    embeddings = OpenAIEmbeddings(model="text-embedding-3-large")

    vectorstore = Chroma(
        collection_name=COLLECTION,
        embedding_function=embeddings,
        persist_directory=DB_PATH
    )

    logger.info("[Vectorstore] Loaded successfully")
    return vectorstore


# 공용 인스턴스
_vectorstore = load_vectorstore()


def search_context(query: str, k: int = 5) -> str:
    """vectorstore에서 query와 관련된 문서를 k개 검색하여 하나의 context 문자열로 반환"""
    docs = _vectorstore.similarity_search(query, k=k)
    logger.info(f"[Vectorstore] 검색된 문서 수: {len(docs)}")

    # 문서 내용만 추출하여 문자열로 합침
    context_text = "\n\n".join([doc.page_content for doc in docs])
    return context_text if context_text else ""
