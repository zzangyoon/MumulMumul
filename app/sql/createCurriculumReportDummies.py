# app/sql/createCurriculumReportDummies.py
import sys
from pathlib import Path

CURRENT_FILE = Path(__file__).resolve()
ROOT_DIR = CURRENT_FILE.parents[2]  # .../MumulMumul
sys.path.append(str(ROOT_DIR))

import random
from datetime import datetime, timedelta, date, time
from bson import BSON
from bson.errors import InvalidDocument
from typing import Any, get_args, get_origin, Union

from pymongo import MongoClient
from sqlalchemy.orm import sessionmaker

from app.core.schemas import Camp, init_db
from app.config import MONGO_URL, MONGO_DB_NAME, SQLITE_URL

# ✅ 네 프로젝트 실제 경로에 맞게 조정
from app.core.mongodb import CurriculumReport
from app.services.curriculum.schemas import (
    CurriculumSummaryCards,
    TopQuestionCategory,
    TopQuestionItem,
    CurriculumAIInsights,
    CurriculumCharts,
    CurriculumTables,
)

COLLECTION_NAME = "curriculum_reports"


# =============================
# AI/RAG 중심 더미 데이터 풀
# =============================
AI_CATEGORIES_IN = [
    "RAG 파이프라인 설계", "Chunking / Splitting", "임베딩 모델 선택",
    "Vector DB(Chroma/FAISS) 운용", "Retriever 튜닝(k, MMR)",
    "Reranker 적용", "Prompt / System 설계", "평가(Evals) & 테스트셋",
    "할루시네이션 방지", "Tool-Using Agent", "LangGraph 라우팅/상태관리",
    "Streaming / WebSocket", "로그/트레이싱(Observability)", "비용/지연 최적화",
]

AI_CATEGORIES_OUT = [
    "GPU/서빙(vLLM/TGI)", "LoRA/FT 개념", "보안/PII 마스킹", "법무/저작권 이슈",
    "MLOps(배포/롤백)", "프로덕트 지표/리텐션", "IR/피칭 자료", "팀 커뮤니케이션/운영",
]

AI_QUESTIONS = [
    "RAG에서 chunk size/overlap을 어떻게 잡아야 검색 품질이 안정적일까요?",
    "MMR 적용했는데 관련 문서가 덜 나오고 다양성만 커진 느낌인데 튜닝 포인트가 뭐예요?",
    "임베딩 모델 바꾸면 기존 벡터 인덱스는 무조건 재생성해야 하나요?",
    "Retriever k를 올리면 recall은 오르는데 답이 길어지고 헛소리가 늘어요. 어떻게 밸런싱하죠?",
    "Reranker는 어디 단계에 붙이는 게 좋아요? latency 대비 효과 측정은 어떻게 해요?",
    "LangGraph에서 interrupts/human-in-the-loop 넣을 때 checkpoint/thread_id 관리는 어떻게 설계하죠?",
    "Tool-using agent가 외부 API를 호출할 때 실패/재시도/타임아웃 정책은 어디서 관리해요?",
    "Streaming 응답에서 중간 토큰이 이상하게 끊기는데 SSE vs WebSocket 선택 기준이 있나요?",
    "대화 로그 저장할 때 Mongo vs SQL 어떤 기준으로 분리하는 게 좋아요?",
    "프롬프트에 컨텍스트를 너무 많이 넣으면 성능이 떨어지는데, 요약/압축 전략 추천해줘요.",
    "할루시네이션을 줄이려면 '답변 금지 조건'을 어디까지 강하게 걸어야 하나요?",
    "평가셋 만들 때 정답이 하나로 고정되지 않는 질문은 어떻게 스코어링하죠?",
    "RAG에서 '타이레놀/tylenol' 같은 표기 변형은 임베딩이 잘 잡아주나요?",
    "운영 환경에서 비용이 튀는데 캐싱은 어느 레벨(리트리버/LLM/최종 응답)에 두는 게 좋아요?",
]

def to_bson_safe(obj):
    """
    PyMongo가 넣을 수 있게 타입 정리:
    - date -> datetime(00:00:00)
    - BaseModel -> dict
    - dict/list 재귀 변환
    """
    # date는 BSON 불가, datetime은 가능
    if isinstance(obj, date) and not isinstance(obj, datetime):
        return datetime.combine(obj, time(0, 0, 0))

    if hasattr(obj, "model_dump"):  # pydantic BaseModel
        return to_bson_safe(obj.model_dump())

    if isinstance(obj, dict):
        return {k: to_bson_safe(v) for k, v in obj.items()}

    if isinstance(obj, list):
        return [to_bson_safe(v) for v in obj]

    return obj



# -----------------------------
# 날짜 유틸: 주차 범위 계산
# -----------------------------
def week_range(camp_start: date, camp_end: date, week_index: int) -> tuple[date, date]:
    start = camp_start + timedelta(days=(week_index - 1) * 7)
    end = start + timedelta(days=6)
    if start < camp_start:
        start = camp_start
    if end > camp_end:
        end = camp_end
    return start, end


# -----------------------------
# Pydantic BaseModel 자동 더미 생성기
# - HardPartDetail / ExtraTopicDetail / PriorityItem
# - CurriculumCharts / CurriculumTables
# -----------------------------
def _is_pydantic_model(tp: Any) -> bool:
    return hasattr(tp, "model_fields") and callable(getattr(tp, "model_validate", None))


def _dummy_primitive(tp: Any):
    if tp is str:
        return random.choice([
            "RAG 품질이 안 올라가요",
            "LangGraph 라우팅 설계가 헷갈려요",
            "retriever 튜닝 포인트가 뭐예요?",
            "reranker 적용 기준이 궁금해요",
            "Evals 구성 어떻게 해요?",
        ])
    if tp is int:
        return random.randint(1, 100)
    if tp is float:
        return round(random.uniform(0, 1), 4)
    if tp is bool:
        return random.choice([True, False])
    if tp is datetime:
        return datetime.utcnow()
    if tp is date:
        return datetime.utcnow().date()
    return None


def dummy_value_for_type(tp: Any, depth: int = 0):
    """
    절대 '필수 필드'에 None이 들어가지 않게 보수적으로 생성한다.
    """
    if depth > 10:
        # 너무 깊어지면 안전한 기본값
        return "N/A"

    origin = get_origin(tp)
    args = get_args(tp)

    # Optional / Union
    if origin is Union:
        non_none = [a for a in args if a is not type(None)]
        return dummy_value_for_type(non_none[0], depth + 1) if non_none else "N/A"

    # Literal (✅ 확실 처리)
    # origin이 typing.Literal 또는 types.Literal일 수 있어서 args로만 판단
    if str(origin) == "typing.Literal" or "Literal" in str(origin):
        return random.choice(list(args)) if args else "N/A"

    # List (✅ typing.List 포함해서 넓게 처리)
    if origin in (list,):
        inner = args[0] if args else str
        # 리스트는 빈 리스트보다 2개 정도 채우는 편이 UI가 보기 좋음
        return [dummy_value_for_type(inner, depth + 1) for _ in range(2)]

    # Dict
    if origin is dict:
        k_tp = args[0] if len(args) > 0 else str
        v_tp = args[1] if len(args) > 1 else str
        key = dummy_value_for_type(k_tp, depth + 1)
        val = dummy_value_for_type(v_tp, depth + 1)
        return {str(key): val}

    # Enum
    if hasattr(tp, "__members__"):
        vals = list(tp)
        return random.choice(vals).value if vals else "N/A"

    # Primitive
    prim = _dummy_primitive(tp)
    if prim is not None:
        return prim

    # Pydantic model
    if _is_pydantic_model(tp):
        return dummy_model(tp, depth + 1)

    # fallback: Unknown 타입은 문자열로
    return "N/A"


def dummy_model(ModelClass: Any, depth: int = 0):
    data = {}
    for name, field in ModelClass.model_fields.items():
        ann = field.annotation

        # ✅ required는 무조건 값 넣기
        if field.is_required():
            data[name] = dummy_value_for_type(ann, depth + 1)
            continue

        # ✅ optional이라도 List면 None 말고 리스트 넣어주기
        if get_origin(ann) in (list,):
            data[name] = dummy_value_for_type(ann, depth + 1)

    # ✅ 여기서도 혹시 None 남아있으면 한번 더 안전망
    for k, v in list(data.items()):
        if v is None:
            data[k] = "N/A"

    return ModelClass(**data)


# -----------------------------
# SummaryCards: AI/RAG 질문/카테고리 기반으로 "정확히" 채움
# -----------------------------
def make_summary_cards(total_questions: int) -> CurriculumSummaryCards:
    curriculum_out_questions = random.randint(0, total_questions // 2)
    curriculum_in_questions = total_questions - curriculum_out_questions
    curriculum_out_ratio = round(curriculum_out_questions / max(total_questions, 1), 4)

    top_question_categories = []
    for c in random.sample(AI_CATEGORIES_IN, k=2):
        top_question_categories.append(
            TopQuestionCategory(
                category=c,
                question_count=random.randint(8, 35),
                scope="in",
            )
        )
    top_question_categories.append(
        TopQuestionCategory(
            category=random.choice(AI_CATEGORIES_OUT),
            question_count=random.randint(5, 25),
            scope="out",
        )
    )

    top_questions = []
    for _ in range(5):
        scope = random.choice(["in", "out"])
        category = random.choice(AI_CATEGORIES_IN if scope == "in" else AI_CATEGORIES_OUT)
        top_questions.append(
            TopQuestionItem(
                question_id=None,
                category=category,
                scope=scope,
                question_text=random.choice(AI_QUESTIONS),
                total_count=random.randint(3, 18),
            )
        )

    return CurriculumSummaryCards(
        total_questions=total_questions,
        curriculum_out_ratio=curriculum_out_ratio,
        curriculum_in_questions=curriculum_in_questions,
        curriculum_out_questions=curriculum_out_questions,
        top_question_categories=top_question_categories,
        top_questions=top_questions,
    )


# -----------------------------
# AIInsights: AI 운영/품질 개선 톤으로 "정확히" 채우고,
# 세부 리스트는 자동 생성기로 안전하게 채움
# -----------------------------
def make_ai_insights() -> CurriculumAIInsights:
    base = {
        "summary_one_line": "이번 주는 RAG 품질(리트리버/리랭커)과 LangGraph 라우팅 설계 질문이 집중되었습니다.",
        "hardest_part_summary": "chunking/검색 튜닝과 hallucination 방지(근거 기반 답변) 설계에서 막힘이 반복되었습니다.",
        "curriculum_out_summary": "서빙/비용/보안(PII) 같은 운영 이슈와, Evals/테스트셋 구축 니즈가 크게 드러났습니다.",
        "improvement_summary": "검색-생성 분리(리트리버 개선) + 간단한 Evals 루프를 먼저 고정하면 품질과 신뢰도가 동시에 올라갑니다.",
        "curriculum_improvement_actions": (
            "1) chunk size/overlap 가이드 + 예시 문서로 기준을 고정하고, "
            "2) retriever(k/MMR) → reranker 적용 유무를 A/B로 비교하며, "
            "3) '근거 없으면 답변 금지' 룰과 출처 표기 템플릿을 공통으로 적용하세요."
        ),
        "extra_session_suggestions": (
            "운영 세션으로 '비용/지연 최적화(캐싱/스트리밍)', "
            "'로그/트레이싱(관측가능성)', 'PII 마스킹/보안'을 짧게 진행하는 것을 추천합니다."
        ),
    }

    tmp = dummy_model(CurriculumAIInsights)
    payload = tmp.model_dump()
    payload.update(base)

    # priority Top3 유지
    if "priority" in CurriculumAIInsights.model_fields:
        priority_ann = CurriculumAIInsights.model_fields["priority"].annotation
        inner = get_args(priority_ann)[0] if get_args(priority_ann) else Any
        payload["priority"] = [dummy_value_for_type(inner) for _ in range(3)]

    # 리스트는 너무 길면 UI 정신없어서 2개 정도로 컷
    if "hardest_parts_detail" in payload and isinstance(payload["hardest_parts_detail"], list):
        payload["hardest_parts_detail"] = payload["hardest_parts_detail"][:2]
    if "extra_topics_detail" in payload and isinstance(payload["extra_topics_detail"], list):
        payload["extra_topics_detail"] = payload["extra_topics_detail"][:2]

    return CurriculumAIInsights(**payload)


# -----------------------------
# Report 한 주치 생성
# charts/tables은 스키마를 여기서 몰라도 자동 생성기로 안전 생성
# -----------------------------
def make_report(camp: Camp, week_index: int) -> CurriculumReport:
    camp_start = camp.start_date.date()
    camp_end = camp.end_date.date()
    w_start, w_end = week_range(camp_start, camp_end, week_index)

    total_questions = random.randint(40, 180)

    summary_cards = make_summary_cards(total_questions)
    ai_insights = make_ai_insights()

    charts = dummy_model(CurriculumCharts)
    tables = dummy_model(CurriculumTables)

    raw_stats = {
        "total_questions": total_questions,
        "unique_students": random.randint(15, 45),
        "curriculum_out_ratio": summary_cards.curriculum_out_ratio,
        "top_signal": random.choice(["retriever 튜닝 수요", "reranker 관심 증가", "LangGraph 상태관리 이슈", "Evals 구축 니즈"]),
        "latency_pain": round(random.uniform(0.1, 0.8), 2),
        "cost_pain": round(random.uniform(0.1, 0.9), 2),
    }

    return CurriculumReport(
        camp_id=camp.camp_id,
        camp_name=camp.name,
        week_index=week_index,
        week_label=f"{week_index}주차",
        week_start=w_start,
        week_end=w_end,
        raw_stats=raw_stats,
        summary_cards=summary_cards,
        charts=charts,
        tables=tables,
        ai_insights=ai_insights,
    )


def insert_dummy_curriculum_reports(
    camp_id: int = 2,
    weeks: int = 6,
    clear_existing: bool = False,
):
    # --- SQLite 연결 ---
    engine = init_db(SQLITE_URL)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = SessionLocal()

    camp = db.query(Camp).filter(Camp.camp_id == camp_id).first()
    if not camp or not camp.start_date or not camp.end_date:
        raise ValueError(f"camp_id={camp_id} not found or missing start/end date")

    # --- Mongo 연결 ---
    client = MongoClient(MONGO_URL)
    mongo_db = client[MONGO_DB_NAME]
    coll = mongo_db[COLLECTION_NAME]

    # 인덱스 (register_mongo_model이 이미 해도 중복 생성 OK)
    coll.create_index([("camp_id", 1)])
    coll.create_index([("week_index", 1)])
    coll.create_index([("created_at", -1)])
    coll.create_index([("camp_id", 1), ("week_index", 1), ("created_at", -1)])

    if clear_existing:
        coll.delete_many({"camp_id": camp_id})
        print(f"🧹 Cleared existing docs for camp_id={camp_id}")

    inserted = 0
    now = datetime.utcnow()

    for w in range(1, weeks + 1):
        report = make_report(camp, w)

        doc = report.model_dump()
        doc["created_at"] = now

        # ✅ 핵심: BSON-safe 변환
        doc = to_bson_safe(doc)

        # ✅ BSON 검증 + 크기 체크 (16MB 제한)
        try:
            encoded = BSON.encode(doc)   # 여기서 InvalidDocument/DocumentTooLarge 잡힘
            size = len(encoded)
            if size > 15_000_000:
                raise ValueError(f"Document too large: {size} bytes (week={w})")
        except InvalidDocument as e:
            raise RuntimeError(f"[Mongo InvalidDocument] week={w} / {e}")
        except Exception as e:
            raise RuntimeError(f"[Mongo Insert Prep Failed] week={w} / {e}")

        coll.insert_one(doc)
        inserted += 1


    db.close()
    client.close()

    print(f"🎉 Done! Inserted {inserted} curriculum reports into '{COLLECTION_NAME}' (camp_id={camp_id}).")


if __name__ == "__main__":
    insert_dummy_curriculum_reports(camp_id=2, weeks=6, clear_existing=False)
