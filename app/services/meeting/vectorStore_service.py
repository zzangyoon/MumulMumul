from langchain_chroma import Chroma
from langchain_core.documents import Document
from app.core.db import SessionLocal
from app.config import settings
from app.services.meeting.embedding_service import EmbeddingService
from typing import List, Dict, Optional
from app.core.logger import setup_logger
from app.core.timezone import format_datetime, timestamp_to_datetime
from app.core.schemas import Meeting

logger = setup_logger(__name__)

class FilterBuilder:
    """ChromaDB 필터 빌더 - 메서드 체이닝 방식"""

    def __init__(self):
        self.filter = {}
        self._db_session = None

    def with_meeting_id(self, meeting_id: Optional[str]):
        """특정 회의로 필터링"""
        if meeting_id:
            self.filter["meeting_id"] = meeting_id
        return self
    
    def with_group_id(self, group_id: Optional[str]):
        """그룹의 모든 회의로 필터링"""
        if group_id:
            db = SessionLocal()
            meetings = db.query(Meeting).filter(
                Meeting.chat_room_id == group_id,
                Meeting.status == "completed"
            ).all()
            db.close()

            if meetings:
                meeting_ids = [m.meeting_id for m in meetings]
                self.filter["meeting_id"] = {"$in" : meeting_ids}
                logger.debug(f"Group filter : {len(meeting_ids)} meetings")
        return self
        
    def with_speaker(self, speaker_name: Optional[str]):
        """특정 발화자로 필터링"""
        if speaker_name:
            self.filter["speaker_name"] = speaker_name
        return self
    
    def with_speakers(self, speaker_names: Optional[List[str]]):
        """여러 발화자로 필터링"""
        if speaker_names:
            self.filter["speaker_name"] = {"$in" : speaker_names}
        return self
    
    def with_type(self, content_type: Optional[str]):
        """컨텐츠 타입으로 필터링 (voice/chat)"""
        if content_type:
            self.filter["type"] = content_type
        return self
    
    def with_custom(self, key: str, value: any):
        """커스텀 필터 추가"""
        if value is not None:
            self.filter[key] = value
        return self
    
    def build(self) -> Optional[Dict]:
        """필터 딕셔너리 반환 (비어있으면 None)"""
        return self.filter if self.filter else None
    
    def __repr__(self):
        return f"FilterBuilder({self.filter})"



class VectorStoreService:
    """ChromaDB 벡터 저장소 서비스"""

    SEGMENTS_COLLECTION = "meeting_segments"
    SUMMARIES_COLLECTION = "meeting_summaries"
    
    def __init__(self):
        """ChromaDB 초기화"""
        self.embedding_function = EmbeddingService.get_instance()
        self.persist_directory = str(settings.VECTORSTORE_DIR / "meetings")
        logger.info(f"VectorStore 초기화: {self.persist_directory}")
    
    # ===== Segment 벡터 저장소 =====
    def get_segments_vectorstore(self) -> Chroma:
        """모든 회의 segments를 저장하는 단일 vectorstore"""
        vectorstore = Chroma(
            collection_name=self.SEGMENTS_COLLECTION,
            embedding_function=self.embedding_function,
            persist_directory=self.persist_directory,
            collection_metadata={
                "type": "segments",
                "description" : "All meeting segments across all meetings"
            }
        )
        return vectorstore
    
    def add_segments_batch(
        self,
        meeting_id: str,
        segments: List[Dict]
    ):
        """배치로 segment 추가"""
        try:
            logger.info(f"Segments 추가 시작: meeting_id={meeting_id}, count={len(segments)}")
            
            vectorstore = self.get_segments_vectorstore()

            documents = []
            ids = []
            
            for seg in segments:
                doc = Document(
                    page_content=seg["text"],
                    metadata={
                        "meeting_id": meeting_id,
                        "segment_id": seg["segment_id"],
                        "user_id": seg["user_id"],
                        "speaker_name": seg["speaker_name"],
                        "absolute_start_ms": seg["absolute_start_ms"],
                        "absolute_end_ms": seg["absolute_end_ms"],
                        "confidence": seg["confidence"],
                        "type": seg.get("type", "voice"),
                        "timestamp": format_datetime(
                            timestamp_to_datetime(seg["absolute_start_ms"]),
                            "%Y-%m-%d %H:%M:%S"
                        ),
                        "timestamp_display": self._format_timestamp_display(seg["start_time_ms"])
                    }
                )
                documents.append(doc)
                ids.append(seg["segment_id"])

            if not documents:
                logger.warning("추가할 document가 없습니다")
                return
            
            # 배치 추가
            vectorstore.add_documents(
                documents=documents,
                ids=ids
            )

            logger.info(f"ChromaDB에 {len(documents)}개 segment 임베딩 추가")

        except Exception as e:
            logger.error(f"Segment 추가 실패: {e}", exc_info=True)
            raise

    def _format_timestamp_display(self, relative_ms: int) -> str:
        """타임스탬프 표시 형식 생성 [MM:SS]"""
        minutes = relative_ms // 60000
        seconds = (relative_ms % 60000) // 1000
        return f"[{minutes:02d}:{seconds:02d}]"


    # 통합 검색 메서드
    def search(
        self,
        query: str,
        k: int = 5,
        meeting_id: Optional[str] = None,
        group_id: Optional[str] = None,
        speaker_name: Optional[str] = None,
        speaker_names: Optional[List[str]] = None,
        content_type: Optional[str] = None,
        custom_filter: Optional[Dict] = None
    ) -> List[Document]:
        """
        통합 검색 메서드 - 모든 검색 시나리오를 커버

        Args:
            query: 검색 쿼리
            k: 반환 개수
            meeting_id: 특정 회의로 제한
            group_id: 특정 그룹으로 제한
            speaker_name: 특정 발화자로 제한
            speaker_names: 여러 발화자로 제한
            content_type: 컨텐츠 타입 (voice/chat)
            custom_filter: 추가 필터
        
        Examples:
            search("API", meeting_id="241211_abc12")    # 특정 회의 검색
            search("API", group_id="team_001")          # 그룹 전체 검색
            search("일정", speaker_name="홍길동")         # 발화자 검색
            search("API", group_id="team_001", speaker_name="홍길동")   # 복합 검색
        """

        try:
            logger.info(f"통합 검색 : query='{query}', k={k}")

            vectorstore = self.get_segments_vectorstore()

            # Filter Builder로 필터 구성
            filter_builder = (
                FilterBuilder()
                .with_meeting_id(meeting_id)
                .with_group_id(group_id)
                .with_speaker(speaker_name)
                .with_speakers(speaker_names)
                .with_type(content_type)
            )

            # 커스텀 필터
            if custom_filter:
                for key, value in custom_filter.items():
                    filter_builder.with_custom(key, value)

            search_filter = filter_builder.build()

            logger.debug(f"검색 필터 : {search_filter}")

            # 검색 실행
            results = vectorstore.similarity_search(
                query = query,
                k = k,
                filter = search_filter
            )
            logger.info(f"검색 완료 : {len(results)}개 결과")
            return results
        
        except Exception as e:
            logger.error(f"검색 실패 : {e}", exc_info=True)
            return []


    def search_segments(
        self,
        meeting_id: str,
        query: str,
        k: int = 5,
        filter_dict: Optional[Dict] = None
    ) -> List[Document]:
        
        """특정 회의 내 segment 검색"""
        return self.search(
            query = query,
            k = k,
            meeting_id = meeting_id,
            custom_filter = filter_dict
        )


    def search_by_group_id(
        self,
        group_id: str,
        query: str,
        k: int = 5
    ) -> List[Document]:
        
        """그룹 회의 검색"""
        return self.search(
            query = query,
            k = k,
            group_id = group_id
        )
        

    def search_all_segments(
        self,
        query: str,
        k: int = 5
    ) -> List[Document]:
        
        """전체 회의 검색"""
        return self.search(query = query, k = k)
        
    
    def search_by_speaker(
        self,
        speaker_name: str,
        query: Optional[str] = None,
        meeting_id: Optional[str] = None,
        group_id: Optional[str] = None,
        k: int = 5
    ) -> List[Document]:
        
        """특정 발화자의 발언 검색"""
        return self.search(
            query = query or "",
            k = k,
            meeting_id = meeting_id,
            group_id = group_id,
            speaker_name = speaker_name
        )

    def search_by_multiple_speakers(
        self,
        speaker_names: List[str],
        query: str,
        meeting_id: Optional[str] = None,
        k: int = 5
    ) -> List[Document]:
        """여러 발화자 검색"""
        return self.search(
            query = query,
            k = k,
            meeting_id = meeting_id,
            speaker_names = speaker_names
        )


    # ===== 요약본 벡터 저장소 (전체) =====
    def get_summaries_vectorstore(self) -> Chroma:
        """ 모든 회의 summaries를 저장하는 단일 vectorstore """
        vectorstore = Chroma(
            collection_name=self.SUMMARIES_COLLECTION,
            embedding_function=self.embedding_function,
            persist_directory=self.persist_directory,
            collection_metadata={
                "type": "summaries",
                "description" : "All meeting summaries"
            }
        )
        return vectorstore
    

    def add_summary(
        self,
        meeting_id: str,
        summary_text: str,
        metadata: Dict
    ):
        """요약본 추가"""
        try:
            logger.info(f"Summary 추가 : meeting_id = {meeting_id}")

            # group_id 조회
            db = SessionLocal()
            meeting = db.query(Meeting).filter(
                Meeting.meeting_id == meeting_id
            ).first()
            db.close()

            group_id = meeting.chat_room_id if meeting else None

            vectorstore = self.get_summaries_vectorstore()

            doc = Document(
                page_content=summary_text,
                metadata={
                    "meeting_id" : meeting_id,
                    "group_id" : group_id,
                    **metadata
                }
            )

            vectorstore.add_documents(
                documents=[doc],
                ids=[f"summary_{meeting_id}"]
            )

            logger.info(f"ChromaDB에 summary 임베딩 추가: {meeting_id}")

        except Exception as e:
            logger.error(f"Summary 추가 실패: {e}", exc_info=True)
            raise

    def search_summaries(
        self,
        query: str,
        k: int = 5,
        meeting_id: Optional[str] = None
    ) -> List[Document]:
        """전체 요약본에서 검색"""
        try:
            vectorstore = self.get_summaries_vectorstore()

            search_filter = None
            if meeting_id:
                search_filter = {"meeting_id" : meeting_id}

            results = vectorstore.similarity_search(
                query = query,
                k = k,
                filter = search_filter
            )
            
            logger.info(f"Summary 검색 완료: {len(results)}개 결과")
            return results

        except Exception as e:
            logger.error(f"Summary 검색 실패: {e}", exc_info=True)
            raise


    def search_summaries_by_group(
        self,
        group_id: str,
        query: str,
        k: int = 3
    ) -> List[Document]:
        """Group의 여러 회의 요약본 검색"""
        try:
            logger.info(f"[VectorStore] Group 요약 검색: {group_id}")

            # 1. SQLite에서 meeting_ids 조회
            db = SessionLocal()
            meetings = db.query(Meeting).filter(
                Meeting.chat_room_id == group_id,
                Meeting.status == "completed"
            ).all()
            db.close()
            
            if not meetings:
                logger.warning(f"Group {group_id}에 해당하는 회의가 없습니다.")
                return []
            
            meeting_ids = [m.meeting_id for m in meetings]
            logger.info(f"발견된 회의 : {len(meeting_ids)}개")
            
            # 2. Global summaries vectorstore에서 검색
            vectorstore = self.get_summaries_vectorstore()
            
            # 3. meeting_id 필터 적용
            results = vectorstore.similarity_search(
                query=query,
                k=k,
                filter={"meeting_id": {"$in": meeting_ids}}
            )
            
            logger.info(f"검색 완료: {len(results)}개 결과")
            return results

        except Exception as e:
            logger.error(f"Group 요약 검색 실패: {e}", exc_info=True)
            return []