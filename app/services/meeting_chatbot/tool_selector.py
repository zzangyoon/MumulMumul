import re
from typing import List, Dict, Optional, Tuple
from app.core.logger import setup_logger
from langchain_core.prompts import ChatPromptTemplate
import json

logger = setup_logger(__name__)


class ToolSelector:
    """
    Tool 선택 전략:
    1. 규칙 기반으로 빠르게 분류 (90% 케이스)
    2. 애매한 경우만 LLM 사용 (10% 케이스)
    """

    # ===================================================================
    # 패턴 정의
    # ===================================================================
    PATTERNS = {
        "get_recent_meetings": [
            r"(지난|최근|이전)\s*(회의|미팅)",
            r"회의\s*(목록|리스트)",
            r"얼마나\s*많은\s*회의",
            r"몇\s*번.*회의"
        ],
        
        "get_meeting_summary": [
            r"요약(해|본)?",
            r"정리(해|본)?",
            r"결정\s*사항",
            r"액션\s*아이템",
            r"핵심\s*내용",
            r"주요\s*포인트",
            r"다음\s*안건"
        ],
        
        "search_meeting_transcript": [
            r"누가.*말했",
            r"누구.*언급",
            r".*에\s*대해.*얘기",
            r".*관련.*내용",
            r"어떤.*발언",
            r".*토론.*내용"
        ],
        
        "get_meeting_context": [
            r"전체.*내용",
            r"상세.*정보",
            r"회의.*전문",
            r"처음부터.*끝까지"
        ]
    }


    # ===================================================================
    # 규칙 기반 선택
    # ===================================================================
    @staticmethod
    def select_by_rule(
        query: str,
        meeting_id: Optional[str] = None,
        group_id: Optional[str] = None
    ) -> Optional[Tuple[str, Dict, float]]:
        """
        규칙 기반 Tool 선택
        
        Returns:
            (tool_name, tool_args, confidence) or None
        """
        query_lower = query.lower().strip()
        
        # 1. meeting_id 명시된 경우
        if meeting_id or re.search(r"회의\s*[\w\d_-]+", query):
            # "회의 241211_abc12 요약해줘"
            for tool_name, patterns in ToolSelector.PATTERNS.items():
                for pattern in patterns:
                    if re.search(pattern, query_lower):
                        if tool_name == "get_recent_meetings":
                            # meeting_id 있으면 요약으로 전환
                            tool_name = "get_meeting_summary"
                        
                        return (
                            tool_name,
                            {"meeting_id": meeting_id} if meeting_id else {},
                            0.9
                        )
        
        # 2. group_id 있는 경우
        if group_id:
            for tool_name, patterns in ToolSelector.PATTERNS.items():
                for pattern in patterns:
                    if re.search(pattern, query_lower):
                        return (
                            tool_name,
                            {"group_id": group_id},
                            0.85
                        )
        
        # 3. 일반 패턴 매칭
        for tool_name, patterns in ToolSelector.PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, query_lower):
                    logger.info(f"[Rule] 매칭: {tool_name} (패턴: {pattern})")
                    
                    args = {}
                    if meeting_id:
                        args["meeting_id"] = meeting_id
                    elif group_id:
                        args["group_id"] = group_id
                    
                    return (tool_name, args, 0.8)
        
        # 패턴 매칭 실패
        return None
    

    # ===================================================================
    # LLM 기반 선택 (Fallback)
    # ===================================================================
    @staticmethod
    async def select_by_llm(
        query: str,
        meeting_id: Optional[str],
        group_id: Optional[str],
        llm
    ) -> Tuple[str, Dict, float]:
        """
        LLM 기반 Tool 선택 (복잡한 질문)
        """
        
        logger.info("[LLM] Tool 선택 요청")
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", """
            당신은 Tool 선택 전문가입니다.

            사용 가능한 Tool:
            1. get_recent_meetings: 최근 회의 목록 조회
            2. get_meeting_summary: 특정 회의 요약본 조회
            3. search_meeting_transcript: 회의 전사본 검색
            4. get_meeting_context: 회의 전체 컨텍스트

            JSON 형식으로 응답하세요:
            {
            "tool": "tool_name",
            "args": {"meeting_id": "...", "group_id": "...", "query": "..."},
            "confidence": 0.0~1.0
            }"""),
                        
            ("human", """
            질문: {query}
            컨텍스트: meeting_id={meeting_id}, group_id={group_id}

            가장 적합한 Tool을 선택하세요.
            """)
        ])
        
        chain = prompt | llm
        
        try:
            response = await chain.ainvoke({
                "query": query,
                "meeting_id": meeting_id or "없음",
                "group_id": group_id or "없음"
            })
            
            # JSON 파싱
            content = response.content.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            
            data = json.loads(content)
            
            return (
                data["tool"],
                data.get("args", {}),
                data.get("confidence", 0.7)
            )
        
        except Exception as e:
            logger.error(f"LLM Tool 선택 실패: {e}")
            # Fallback: 검색
            return ("search_meeting_transcript", {"query": query}, 0.5)
        

    
    # ===================================================================
    # 통합 선택 (Hybrid)
    # ===================================================================
    @staticmethod
    async def select_tool(
        query: str,
        meeting_id: Optional[str],
        group_id: Optional[str],
        llm
    ) -> Tuple[str, Dict, float]:
        """
        하이브리드 Tool 선택
        """
        # 1단계: 규칙 기반 시도
        result = ToolSelector.select_by_rule(query, meeting_id, group_id)
        
        if result:
            tool_name, args, confidence = result
            logger.info(f"[Rule] 선택 완료: {tool_name} (신뢰도: {confidence})")
            return result
        
        # 2단계: LLM Fallback
        logger.info("[Fallback] LLM 기반 선택")
        return await ToolSelector.select_by_llm(query, meeting_id, group_id, llm)
    

    # ===================================================================
    # 다중 Tool 선택
    # ===================================================================
    @staticmethod
    async def select_multiple_tools(
        query: str,
        meeting_id: Optional[str],
        group_id: Optional[str],
        llm
    ) -> List[Tuple[str, Dict, float]]:
        """
        여러 Tool을 순차 실행해야 하는 경우
        
        예: "지난 회의 요약해줘" → [get_recent_meetings, get_meeting_summary]
        """
        query_lower = query.lower()
        tools = []
        
        # 패턴 1: "지난 회의 요약"
        if re.search(r"(지난|최근).*회의.*요약", query_lower):
            logger.info("[Multi] 지난 회의 → 요약 파이프라인")
            
            tools.append((
                "get_recent_meetings",
                {"group_id": group_id, "limit": 1} if group_id else {"limit": 1},
                0.9
            ))
            
            tools.append((
                "get_meeting_summary",
                {},  # 첫 번째 결과의 meeting_id 사용
                0.9
            ))
            
            return tools
        
        # 패턴 2: 단일 Tool
        single = await ToolSelector.select_tool(query, meeting_id, group_id, llm)
        return [single]