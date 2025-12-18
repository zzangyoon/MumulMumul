from datetime import datetime
import json
from typing import Dict, Any, Optional, List

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from langchain_core.output_parsers import PydanticOutputParser

from app.services.attendance.schemas import AttendanceRuleset

parser = PydanticOutputParser(pydantic_object=AttendanceRuleset)

format_instructions = parser.get_format_instructions()

def compile_ruleset_with_llm(raw_rules_text: str) -> AttendanceRuleset:
    """
    운영진 자연어 규칙을 표준 JSON(Ruleset DSL)로 컴파일한다.
    - 복잡한 체계는 나중에 확장 가능
    - 지금은 최소 스키마만 고정
    """

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

    prompt = f"""
    너는 부트캠프 출결 규칙을 "표준 JSON 규칙"으로 컴파일하는 컴파일러다.
    아래 운영진 규칙 텍스트를 읽고, 반드시 JSON만 출력해라(설명 금지).

    [운영진 규칙 텍스트]
    {raw_rules_text}

    [출력 JSON 스키마]
    {format_instructions}

    규칙 텍스트에 없는 항목은 합리적인 기본값을 쓰되,
    애매하거나 충돌 가능성이 있으면:

    반드시 JSON만 출력해라.
    """

    msg = llm.invoke(prompt).content

    return msg