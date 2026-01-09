"""
LLM 기반 Decision Maker

기존 규칙 기반(decision_maker.py)과 별도로 운영.
LLM이 Intent + Entity를 직접 추출.
"""

import json
from typing import Optional, List
from langchain_core.prompts import ChatPromptTemplate
from app.core.logger import setup_logger
from .agent_structures import Decision
from .semantic_cache import get_semantic_cache

logger = setup_logger(__name__)


class LLMDecisionMaker:
    """
    LLM 기반 Decision Maker (시맨틱 캐싱 적용)

    흐름:
    1. 캐시 조회 (유사 질문 검색)
    2. Cache HIT → 캐시된 Decision 반환
    3. Cache MISS → LLM 호출 → 캐시 저장
    
    - 규칙 기반 대비 정확도 향상
    - 다양한 표현 인식 가능
    - 복합 의도 분해 가능
    """

    SYSTEM_PROMPT = """
    
    당신은 회의 도우미 Agent의 Intent Router입니다.

    사용자의 질문을 분석하여 적절한 Tool과 파라미터를 결정하세요.

    ## 사용 가능한 Tools

    1. **get_recent_meetings**: 최근 회의 목록 조회
    - 파라미터: group_id(선택), limit(기본 5), start_date, end_date
    - 예: "지난 회의들 보여줘", "이번 주 회의 목록", "12월 회의"

    2. **get_meeting_summary**: 특정 회의 요약본 조회
    - 파라미터: meeting_id(선택), group_id(선택)
    - 예: "회의 요약해줘", "결정사항 알려줘", "액션 아이템 뭐야"

    3. **search_meeting_transcript**: 회의 내용 검색 (벡터 검색)
    - 파라미터: query(필수), meeting_id(선택), group_id(선택), k(기본 5)
    - 예: "API 개발 관련해서 뭐라고 했어?", "예산 얘기 나온 부분"

    4. **search_by_speaker**: 특정 발화자 발언 검색
    - 파라미터: speaker_name(필수), query(선택), meeting_id(선택), group_id(선택)
    - 예: "철수가 뭐라고 했어?", "김팀장 의견이 뭐였지?"

    5. **get_meeting_context**: 회의 전체 컨텍스트 조회
    - 파라미터: meeting_id(선택)
    - 예: "회의 전체 내용 보여줘", "처음부터 끝까지 알려줘"

    ## 응답 규칙

    1. 반드시 JSON 형식으로만 응답
    2. 여러 Tool이 필요하면 actions 배열에 순서대로 추가
    3. "지난 회의 요약해줘"처럼 회의 특정 + 작업이 필요하면 2개 Action 사용
    4. Entity 추출 시 원문 그대로 사용 (예: "철수" → "철수")

    ## 응답 형식

    ```json
    {{
    "actions": [
        {{
        "tool": "tool_name",
        "args": {{"param1": "value1"}},
        "reasoning": "왜 이 tool을 선택했는지"
        }}
    ],
    "confidence": 0.0~1.0
    }}
    ```
    """

    USER_PROMPT = """
    
    질문: {query}

    컨텍스트:
    - meeting_id: {meeting_id}
    - group_id: {group_id}

    위 질문에 적합한 Tool과 파라미터를 결정하세요.
    """


    @staticmethod
    async def make_decision(
        query: str,
        meeting_id: Optional[str],
        group_id: Optional[str],
        llm,
        use_cache: bool = True  # 캐싱 활성화 옵션
    ) -> List[Decision]:
        """
        LLM 기반 Decision 생성 (시맨틱 캐싱 적용)
        
        Returns:
            List[Decision]: 실행할 Decision 목록
        """
        logger.info(f"[LLM Decision] query: {query}")

        cache = get_semantic_cache()

        # ===== 1. 캐시 조회 =====
        if use_cache:
            cache_result = await cache.get(query, meeting_id, group_id)
            
            if cache_result:
                cached_decisions, similarity = cache_result
                
                # 캐시된 Decision 복원
                decisions = []
                for d in cached_decisions:
                    # meeting_id, group_id 갱신 (현재 컨텍스트로)
                    entities = d.get("entities", {}).copy()
                    if meeting_id:
                        entities["meeting_id"] = meeting_id
                    if group_id:
                        entities["group_id"] = group_id
                    
                    decision = Decision(
                        intent=d["intent"],
                        confidence=d.get("confidence", 0.8),
                        entities=entities,
                        reasoning=f"[Cached] {d.get('reasoning', '')} (similarity={similarity:.3f})"
                    )
                    decisions.append(decision)
                
                logger.info(f"[Cache HIT] {len(decisions)} decisions 반환")
                return decisions

        # ===== 2. LLM 호출 (Cache MISS) =====
        logger.info("[Cache MISS] LLM 호출")

        prompt = ChatPromptTemplate.from_messages([
            ("system", LLMDecisionMaker.SYSTEM_PROMPT),
            ("human", LLMDecisionMaker.USER_PROMPT)
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
            
            # ```json 블록 제거
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            data = json.loads(content)

            # Decision 목록 생성
            decisions = []
            decisions_for_cache = []  # 캐시용 (dict 형태)

            for action in data.get("actions", []):
                # 기본 entities 구성
                entities = action.get("args", {})
                
                # meeting_id, group_id 주입 (없으면)
                if meeting_id and "meeting_id" not in entities:
                    entities["meeting_id"] = meeting_id
                if group_id and "group_id" not in entities:
                    entities["group_id"] = group_id

                decision = Decision(
                    intent=action["tool"],
                    confidence=data.get("confidence", 0.8),
                    entities=entities,
                    reasoning=action.get("reasoning", "LLM 기반 결정")
                )
                decisions.append(decision)

                # 캐시용 데이터 (meeting_id, group_id 제외 - 컨텍스트 독립적)
                cache_entities = {
                    k: v for k, v in action.get("args", {}).items()
                    if k not in ("meeting_id", "group_id")
                }
                decisions_for_cache.append({
                    "intent": action["tool"],
                    "confidence": data.get("confidence", 0.8),
                    "entities": cache_entities,
                    "reasoning": action.get("reasoning", "LLM 기반 결정")
                })

                logger.info(f"  → {decision.intent}: {decision.entities}")

            if not decisions:
                # Fallback: 검색으로 처리
                logger.warning("LLM이 빈 응답 반환 → fallback")
                decisions.append(Decision(
                    intent="search_meeting_transcript",
                    confidence=0.5,
                    entities={"query": query, "meeting_id": meeting_id, "group_id": group_id},
                    reasoning="LLM 빈 응답 fallback"
                ))
            else:
                # ===== 3. 캐시 저장 =====
                if use_cache:
                    await cache.set(query, decisions_for_cache, meeting_id, group_id)

            return decisions

        except json.JSONDecodeError as e:
            logger.error(f"JSON 파싱 실패: {e}")
            logger.error(f"원본 응답: {response.content}")
            return [Decision(
                intent="search_meeting_transcript",
                confidence=0.5,
                entities={"query": query},
                reasoning=f"JSON 파싱 실패 fallback: {str(e)}"
            )]

        except Exception as e:
            logger.error(f"LLM Decision 실패: {e}", exc_info=True)
            return [Decision(
                intent="search_meeting_transcript",
                confidence=0.5,
                entities={"query": query},
                reasoning=f"LLM 오류 fallback: {str(e)}"
            )]