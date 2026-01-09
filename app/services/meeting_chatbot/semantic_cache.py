"""
시맨틱 캐싱 서비스

유사한 질문에 대해 LLM Decision을 캐싱하여 속도/비용 최적화.
임베딩 유사도 기반으로 캐시 히트 판단.
"""

import hashlib
import json
import time
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, asdict
from langchain_openai import OpenAIEmbeddings
from app.core.logger import setup_logger
from app.config import settings

logger = setup_logger(__name__)


@dataclass
class CacheEntry:
    """캐시 엔트리"""
    query: str
    embedding: List[float]
    decisions: List[Dict[str, Any]]  # Decision.to_dict() 결과
    created_at: float
    hit_count: int = 0
    last_hit_at: float = None


class SemanticCache:
    """
    시맨틱 캐싱 서비스

    유사한 질문에 대해 LLM Decision을 캐싱하여 속도/비용 최적화
    임베딩 유사도 기반 캐시 히트 판단
    - TTL 기반 캐시 만료
    - LRU 기반 캐시 정리
    """
    
    def __init__(
        self,
        similarity_threshold: float = 0.75,
        ttl_seconds: int = 3600,  # 1시간
        max_cache_size: int = 1000
    ):
        self.similarity_threshold = similarity_threshold
        self.ttl_seconds = ttl_seconds
        self.max_cache_size = max_cache_size
        
        # 캐시 저장소 (메모리 기반)
        self._cache: Dict[str, CacheEntry] = {}
        
        # 임베딩 모델
        self._embeddings = OpenAIEmbeddings(
            model=settings.EMBEDDING_MODEL,
            api_key=settings.OPENAI_API_KEY
        )
        
        # 통계
        self._stats = {
            "hits": 0,
            "misses": 0,
            "total_queries": 0
        }
        
        logger.info(
            f"SemanticCache 초기화: "
            f"threshold={similarity_threshold}, "
            f"ttl={ttl_seconds}s, "
            f"max_size={max_cache_size}"
        )
    
    def _compute_embedding(self, text: str) -> List[float]:
        """텍스트 임베딩 생성"""
        return self._embeddings.embed_query(text)
    
    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """코사인 유사도 계산"""
        import numpy as np
        v1, v2 = np.array(vec1), np.array(vec2)
        return float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2)))
    
    def _generate_cache_key(self, query: str, context: Dict) -> str:
        """캐시 키 생성 (컨텍스트 포함)"""
        # meeting_id, group_id가 다르면 다른 캐시
        context_str = json.dumps(context, sort_keys=True)
        combined = f"{query}|{context_str}"
        return hashlib.md5(combined.encode()).hexdigest()
    
    def _find_similar_entry(
        self,
        query_embedding: List[float],
        context: Dict
    ) -> Optional[Tuple[str, CacheEntry, float]]:
        """
        유사한 캐시 엔트리 검색
        
        Returns:
            (cache_key, entry, similarity) or None
        """
        best_match = None
        best_similarity = 0.0
        
        current_time = time.time()
        
        for key, entry in self._cache.items():
            # TTL 체크
            if current_time - entry.created_at > self.ttl_seconds:
                continue
            
            # 유사도 계산
            similarity = self._cosine_similarity(query_embedding, entry.embedding)
            
            if similarity >= self.similarity_threshold and similarity > best_similarity:
                best_similarity = similarity
                best_match = (key, entry, similarity)
        
        return best_match
    
    def _cleanup_expired(self):
        """만료된 캐시 정리"""
        current_time = time.time()
        expired_keys = [
            key for key, entry in self._cache.items()
            if current_time - entry.created_at > self.ttl_seconds
        ]
        
        for key in expired_keys:
            del self._cache[key]
        
        if expired_keys:
            logger.debug(f"만료된 캐시 {len(expired_keys)}개 정리")
    
    def _evict_lru(self):
        """LRU 방식으로 캐시 정리"""
        if len(self._cache) <= self.max_cache_size:
            return
        
        # last_hit_at 기준 정렬, 가장 오래된 것 제거
        sorted_entries = sorted(
            self._cache.items(),
            key=lambda x: x[1].last_hit_at or x[1].created_at
        )
        
        # 20% 제거
        remove_count = len(self._cache) // 5
        for key, _ in sorted_entries[:remove_count]:
            del self._cache[key]
        
        logger.info(f"LRU 캐시 정리: {remove_count}개 제거")
    
    async def get(
        self,
        query: str,
        meeting_id: Optional[str] = None,
        group_id: Optional[str] = None
    ) -> Optional[Tuple[List[Dict], float]]:
        """
        캐시에서 Decision 조회
        
        Returns:
            (decisions, similarity) or None
        """
        self._stats["total_queries"] += 1
        
        context = {"meeting_id": meeting_id, "group_id": group_id}
        
        # 임베딩 생성
        query_embedding = self._compute_embedding(query)
        
        # 유사한 엔트리 검색
        result = self._find_similar_entry(query_embedding, context)
        
        if result:
            cache_key, entry, similarity = result
            
            # 히트 통계 업데이트
            entry.hit_count += 1
            entry.last_hit_at = time.time()
            self._stats["hits"] += 1
            
            logger.info(
                f"[Cache HIT] similarity={similarity:.3f}, "
                f"original='{entry.query[:30]}...', "
                f"hit_count={entry.hit_count}"
            )
            
            return (entry.decisions, similarity)
        
        self._stats["misses"] += 1
        logger.debug(f"[Cache MISS] query='{query[:30]}...'")
        return None
    
    async def set(
        self,
        query: str,
        decisions: List[Dict],
        meeting_id: Optional[str] = None,
        group_id: Optional[str] = None
    ):
        """
        Decision을 캐시에 저장
        """
        context = {"meeting_id": meeting_id, "group_id": group_id}
        cache_key = self._generate_cache_key(query, context)
        
        # 임베딩 생성
        query_embedding = self._compute_embedding(query)
        
        # 캐시 엔트리 생성
        entry = CacheEntry(
            query=query,
            embedding=query_embedding,
            decisions=decisions,
            created_at=time.time(),
            hit_count=0,
            last_hit_at=None
        )
        
        self._cache[cache_key] = entry
        
        logger.debug(f"[Cache SET] query='{query[:30]}...'")
        
        # 정리
        self._cleanup_expired()
        self._evict_lru()
    
    def get_stats(self) -> Dict[str, Any]:
        """캐시 통계 반환"""
        hit_rate = (
            self._stats["hits"] / self._stats["total_queries"] * 100
            if self._stats["total_queries"] > 0 else 0
        )
        
        return {
            "total_queries": self._stats["total_queries"],
            "hits": self._stats["hits"],
            "misses": self._stats["misses"],
            "hit_rate": f"{hit_rate:.1f}%",
            "cache_size": len(self._cache),
            "max_size": self.max_cache_size
        }
    
    def clear(self):
        """캐시 전체 삭제"""
        self._cache.clear()
        self._stats = {"hits": 0, "misses": 0, "total_queries": 0}
        logger.info("캐시 전체 삭제됨")


# 싱글톤 인스턴스
_semantic_cache: Optional[SemanticCache] = None


def get_semantic_cache() -> SemanticCache:
    """싱글톤 캐시 인스턴스 반환"""
    global _semantic_cache
    if _semantic_cache is None:
        _semantic_cache = SemanticCache()
    return _semantic_cache
