from datetime import datetime
import json
from typing import Dict, Any, Optional, List

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser

from app.core.models import openai_chat_model
from app.services.attendance.schemas import CompileRuleset

parser = PydanticOutputParser(pydantic_object=CompileRuleset)

format_instructions = parser.get_format_instructions()

parser = PydanticOutputParser(pydantic_object=CompileRuleset)
format_instructions = parser.get_format_instructions()

def compile_ruleset_with_llm(raw_rules_text: str) -> CompileRuleset:
    """
    운영진 자연어 규칙을 표준 JSON(Ruleset DSL)로 컴파일한다.
    - 복잡한 체계는 나중에 확장 가능
    - 지금은 최소 스키마만 고정
    """

    llm = openai_chat_model()

    system_prompt = """
    너는 부트캠프 출결 규칙을 "표준 JSON 규칙"으로 컴파일하는 컴파일러다.
    제공되는 운영진 규칙 텍스트를 읽고, 반드시 JSON만 출력해라(설명 금지).

    [출력 형식]
    {format_instructions}

    규칙 텍스트에 없는 항목은 합리적인 기본값을 사용해라.
    반드시 JSON만 출력해라.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", """
            규칙 텍스트를 분석하여 JSON을 출력해라.
         
            [운영진 규칙 텍스트]
            {raw_rules_text}
        """),
    ])

    llm_chain = prompt | llm | parser

    result = llm_chain.invoke({
        "raw_rules_text": raw_rules_text,
        "format_instructions": format_instructions,
    })

    return result