import re
from typing import List, Optional, Tuple
from app.core.logger import setup_logger
from langchain_core.prompts import ChatPromptTemplate
from .agent_structures import Decision, IntentType
from datetime import datetime
from calendar import monthrange
import json

logger = setup_logger(__name__)


class DecisionMaker:
    """
    Agent의 Decision Making 담당

    규칙 기반(90%) + LLM(10%) 하이브리드 방식
    """

    # ===================================================================
    # 패턴 우선순위 정의 (숫자가 높을수록 우선)
    # ===================================================================
    PATTERN_PRIORITY = {
        "get_recent_meetings": 100,
        "search_by_speaker": 95,
        "search_meeting_transcript": 90,
        "get_meeting_context": 80,
        "get_meeting_summary": 70,
    }

    # ===================================================================
    # 패턴 정의
    # ===================================================================
    PATTERNS = {
        "get_recent_meetings": [
            r"(지난|최근|이전)\s*(회의|미팅)",
            r"회의\s*(목록|리스트)",
            r"얼마나\s*많은\s*회의",
            r"몇\s*번.*회의",
            r"\d{4}년\s*\d{1,2}월\s*\d{1,2}일.*회의",
            r"\d{1,2}월\s*\d{1,2}일.*회의",
            r"\d{4}년\s*\d{1,2}월.*몇\s*건",
            r"\d{1,2}월.*몇\s*건",
            r"\d{4}년\s*\d{1,2}월.*회의",
            r"\d{1,2}월.*회의"
        ],

        "search_by_speaker": [
            r"(누가|누구).*(말했|언급|얘기)",
            r"[\w가-힣]+\s*(이|가)\s*.*(말|얘기|언급)",
            r"[\w가-힣]+\s*의\s*(의견|생각|말)",
            r"[\w가-힣]+\s*.*(뭐라고|무슨\s*말)"
        ],
        
        "get_meeting_summary": [
            r"^요약(해|본)?\??$",
            r"^정리(해|본)?\??$",
            # r"요약(해|본)?",
            # r"정리(해|본)?",
            r"결정\s*사항",
            r"액션\s*아이템",
            r"핵심\s*내용",
            r"주요\s*포인트",
            r"다음\s*안건",
            r"^뭐야\??$",
            # r"뭐(야|였어|였지)",
            r"무엇"
        ],
        
        "search_meeting_transcript": [
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
    # Entity 추출 패턴
    # ===================================================================
    ENTITY_PATTERNS = {
        "speaker": r"([\w가-힣]+?)(?:이|가|의)?\s*(?:뭐라고|말했|얘기|의견|언급)",
        "topic": r"([\w가-힣]+)\s*(에\s*대해|관련|관해서)",
        "meeting_id": r"회의\s*([\w\d_-]+)",
        "full_date": r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일",
        "year_month": r"(\d{4})년\s*(\d{1,2})월",
        "month_day": r"(\d{1,2})월\s*(\d{1,2})일",
        "month_only": r"(\d{1,2})월"
    }


    # ===================================================================
    # 규칙 기반 Decision
    # ===================================================================
    @staticmethod
    def make_decision_by_rule(
        query: str,
        meeting_id: Optional[str] = None,
        group_id: Optional[str] = None
    ) -> Optional[Decision]:
        """
        규칙 기반 Decision 생성
        
        Returns:
            Decision 객체 or None (매칭 실패시)
        """
        query_lower = query.lower().strip()

        # Entity 추출
        entities = DecisionMaker._extract_entities(query, meeting_id, group_id)

        matches = []
        
        # 1. meeting_id 명시된 경우
        if meeting_id or re.search(r"회의\s*[\w\d_-]+", query):
            # "회의 241211_abc12 요약해줘"
            for tool_name, patterns in DecisionMaker.PATTERNS.items():
                for pattern in patterns:
                    if re.search(pattern, query_lower):
                        priority = DecisionMaker.PATTERN_PRIORITY.get(tool_name, 0)
                        matches.append((priority, tool_name, pattern))
            
            if matches:
                # 우선순위 높은 것 선택
                matches.sort(reverse=True, key=lambda x: x[0])
                _, tool_name, pattern = matches[0]
                
                if tool_name == "get_recent_meetings":
                    tool_name = "get_meeting_summary"
                
                logger.info(f"[Rule] 매칭: {tool_name} (패턴: {pattern}, 우선순위: {matches[0][0]})")
                
                return Decision(
                    intent=tool_name,
                    confidence=0.9,
                    entities=entities,
                    reasoning=f"규칙 매칭: meeting_id 명시 + 패턴 '{pattern}' (우선순위: {matches[0][0]})"
                )
        
        # 2. group_id 있는 경우
        if group_id:
            for tool_name, patterns in DecisionMaker.PATTERNS.items():
                for pattern in patterns:
                    if re.search(pattern, query_lower):
                        priority = DecisionMaker.PATTERN_PRIORITY.get(tool_name, 0)
                        matches.append((priority, tool_name, pattern))
            
            if matches:
                matches.sort(reverse=True, key=lambda x: x[0])
                _, tool_name, pattern = matches[0]
                
                logger.info(f"[Rule] 매칭: {tool_name} (패턴: {pattern}, 우선순위: {matches[0][0]})")
                
                return Decision(
                    intent=tool_name,
                    confidence=0.85,
                    entities=entities,
                    reasoning=f"규칙 매칭: group_id 존재 + 패턴 '{pattern}' (우선순위: {matches[0][0]})"
                )
        
        # 3. 일반 패턴 매칭
        for tool_name, patterns in DecisionMaker.PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, query_lower):
                    priority = DecisionMaker.PATTERN_PRIORITY.get(tool_name, 0)
                    matches.append((priority, tool_name, pattern))
        
        if matches:
            # 우선순위 높은 것 선택
            matches.sort(reverse=True, key=lambda x: x[0])
            _, tool_name, pattern = matches[0]
            
            logger.info(f"[Rule] 매칭: {tool_name} (패턴: {pattern}, 우선순위: {matches[0][0]})")
            
            return Decision(
                intent=tool_name,
                confidence=0.8,
                entities=entities,
                reasoning=f"규칙 매칭: 패턴 '{pattern}' (우선순위: {matches[0][0]})"
            )
        
        # 패턴 매칭 실패
        return None
    

    @staticmethod
    def _extract_entities(
        query: str,
        meeting_id: Optional[str] = None,
        group_id: Optional[str] = None
    ) -> dict:
        """쿼리에서 Entity 추출"""
        entities = {}

        # meeting_id, group_id
        if meeting_id:
            entities["meeting_id"] = meeting_id
        if group_id:
            entities["group_id"] = group_id

        # 발화자 추출
        speaker_match = re.search(
            DecisionMaker.ENTITY_PATTERNS["speaker"],
            query
        )
        if speaker_match:
            entities["speaker"] = speaker_match.group(1)
            logger.debug(f"발화자 추출: {entities['speaker']}")

        # 토픽 추출
        topic_match = re.search(
            DecisionMaker.ENTITY_PATTERNS["topic"],
            query
        )
        if topic_match:
            entities["topic"] = topic_match.group(1)

        # 날짜 추출
        full_date_match = re.search(
            DecisionMaker.ENTITY_PATTERNS["full_date"],
            query
        )
        if full_date_match:
            year, month, day = full_date_match.groups()
            entities["start_date"] = f"{year}-{int(month):02d}-{int(day):02d}T00:00:00"
            entities["end_date"] = f"{year}-{int(month):02d}-{int(day):02d}T23:59:59"
            logger.debug(f"날짜 추출 : {entities['start_date']} ~ {entities['end_date']}")

        # "2025년 12월" 형식 (전체 월)
        elif re.search(DecisionMaker.ENTITY_PATTERNS["year_month"], query):
            year_month_match = re.search(DecisionMaker.ENTITY_PATTERNS["year_month"], query)
            year, month = year_month_match.groups()
            
            # 해당 월의 첫날과 마지막 날
            last_day = monthrange(int(year), int(month))[1]
            
            entities["start_date"] = f"{year}-{int(month):02d}-01T00:00:00"
            entities["end_date"] = f"{year}-{int(month):02d}-{last_day}T23:59:59"
            logger.debug(f"월 추출: {entities['start_date']} ~ {entities['end_date']}")
        
        # "12월 30일" 형식 (올해로 가정)
        elif re.search(DecisionMaker.ENTITY_PATTERNS["month_day"], query):
            month_day_match = re.search(DecisionMaker.ENTITY_PATTERNS["month_day"], query)
            month, day = month_day_match.groups()
            current_year = datetime.now().year
            
            entities["start_date"] = f"{current_year}-{int(month):02d}-{int(day):02d}T00:00:00"
            entities["end_date"] = f"{current_year}-{int(month):02d}-{int(day):02d}T23:59:59"
            logger.debug(f"날짜 추출 (올해): {entities['start_date']} ~ {entities['end_date']}")
        
        # "12월" 형식 (올해 해당 월)
        elif re.search(DecisionMaker.ENTITY_PATTERNS["month_only"], query):
            month_match = re.search(DecisionMaker.ENTITY_PATTERNS["month_only"], query)
            month = month_match.group(1)
            current_year = datetime.now().year
            last_day = monthrange(current_year, int(month))[1]
            
            entities["start_date"] = f"{current_year}-{int(month):02d}-01T00:00:00"
            entities["end_date"] = f"{current_year}-{int(month):02d}-{last_day}T23:59:59"
            logger.debug(f"월 추출 (올해): {entities['start_date']} ~ {entities['end_date']}")

        # 쿼리 원문 저장
        entities["query"] = query

        return entities
    

    # ===================================================================
    # LLM 기반 Decision (Fallback)
    # ===================================================================
    @staticmethod
    async def make_decision_by_llm(
        query: str,
        meeting_id: Optional[str],
        group_id: Optional[str],
        llm
    ) -> Decision:
        """
        LLM 기반 Decision 생성 (복잡한 질문)
        """
        
        logger.info("[LLM] Decision 요청")
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", """
            당신은 회의 도우미 Agent의 Decision Maker입니다.

            사용 가능한 Intent:
            1. get_recent_meetings: 최근 회의 목록 조회
            2. get_meeting_summary: 특정 회의 요약본 조회
            3. search_meeting_transcript: 회의 전사본 검색
            4. search_by_speaker: 특정 발화자 발언 검색
            5. get_meeting_context: 회의 전체 컨텍스트

            JSON 형식으로 응답하세요:
            {{
              "intent": "tool_name",
              "confidence": 0.0~1.0,
              "entities": {{"meeting_id": "...", "speaker": "...", "topic": "..."}},
              "reasoning": "왜 이 intent를 선택했는지"
            }}"""),
                        
            ("human", """
            질문: {query}
            컨텍스트: meeting_id={meeting_id}, group_id={group_id}

            가장 적합한 Intent를 결정하세요.
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
            
            return Decision(
                intent = data["intent"],
                confidence = data.get("confidence", 0.7),
                entities = data.get("entities", {}),
                reasoning = data.get("reasoning", "LLM 기반 결정")
            )
        
        except Exception as e:
            logger.error(f"LLM Decision 실패: {e}")
            # Fallback: 검색으로 처리
            return Decision(
                intent="search_meeting_transcript",
                confidence=0.5,
                entities={"query": query},
                reasoning=f"LLM 실패 폴백 ({str(e)})"
            )
        

    
    # ===================================================================
    # 통합 Decision (Hybrid)
    # ===================================================================
    @staticmethod
    async def make_decision(
        query: str,
        meeting_id: Optional[str],
        group_id: Optional[str],
        llm
    ) -> Decision:
        """
        하이브리드 Decision 생성

        1단계 : 규칙 기반 시도 (빠름)
        2단계 : LLM Fallback (느림)
        """
        # 1단계: 규칙 기반
        decision = DecisionMaker.make_decision_by_rule(query, meeting_id, group_id)

        if decision:
            logger.info(f"[Rule] Decision 완료 : {decision}")
            return decision
        
        # 2단계: LLM Fallback
        logger.info("[Fallback] LLM 기반 Decision")
        decision = await DecisionMaker.make_decision_by_llm(
            query, meeting_id, group_id, llm
        )
        logger.info(f"[LLM] Decision 완료 : {decision}")
        return decision
    

    # ===================================================================
    # 다중 Tool 결정 (Sequential Actions)
    # ===================================================================
    @staticmethod
    async def make_multi_decisions(
        query: str,
        meeting_id: Optional[str],
        group_id: Optional[str],
        llm
    ) -> List[Decision]:
        """
        여러 Action이 필요한 경우
        
        예: "지난 회의 요약해줘" → [get_recent_meetings, get_meeting_summary]
        """
        query_lower = query.lower()
        decisions = []
        
        # 패턴 1: "지난 회의 요약" (다중 Action)
        if re.search(r"(지난|최근|이전)\s*(회의|미팅)", query_lower):
            logger.info("[Multi] 지난 회의 → 요약 파이프라인")

            # Entity 추출 (speaker 포함)
            entities = DecisionMaker._extract_entities(query, meeting_id, group_id)
            
            # Decision 1 : 최근 회의 조회
            decisions.append(Decision(
                intent = "get_recent_meetings",
                confidence = 0.9,
                entities = {"group_id": group_id, "limit": 1} if group_id else {"limit": 1},
                reasoning = "다중 액션 : 최근 회의 조회"
            ))
            
            # Decision 2 : 의도별 분기
            if re.search(r"(요약|정리|결정|액션|핵심)", query_lower):
                next_intent = "get_meeting_summary"
                next_entities = {}
            elif re.search(r"(누가|뭐라고|말했|언급)", query_lower):
                next_intent = "search_by_speaker"
                next_entities = {"speaker_name": entities.get("speaker", "")}
            elif re.search(r"(전체|전문|처음부터)", query_lower):
                next_intent = "get_meeting_context"
                next_entities = {}
            else:
                next_intent = "search_meeting_transcript"
                next_entities = {"query": query}

            decisions.append(Decision(
                intent=next_intent,
                confidence=0.85,
                entities=next_entities,
                reasoning="지난 회의 기반 후속 질의"
            ))
            
            return decisions
        
        # 패턴 2: meeting_id 명시 + 요약 요청 (단일 Action)
        if meeting_id and re.search(r"(요약|정리|알려)", query_lower):
            logger.info("[Single] meeting_id 명시 → 직접 요약 조회")
            decisions.append(Decision(
                intent="get_meeting_summary",
                confidence=0.9,
                entities={"meeting_id": meeting_id, "query": query},
                reasoning="단일 액션: 직접 요약 조회"
            ))
            return decisions

        # 패턴 3: 단일 Decision
        single = await DecisionMaker.make_decision(query, meeting_id, group_id, llm)
        return [single]