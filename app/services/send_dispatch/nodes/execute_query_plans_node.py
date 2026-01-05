import sys
from pathlib import Path

CURRENT_FILE = Path(__file__).resolve()
ROOT_DIR = CURRENT_FILE.parents[4]   # .../MumulMumul
sys.path.append(str(ROOT_DIR))

from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, date

from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.core.db import get_db
from app.core.schemas import User, Camp, UserType, AttendanceDaily, SessionActivityLog
from app.services.send_dispatch.schemas import MessagingAgentState

# (선택) fallback tool 사용
try:
    from app.tools.db_tools import get_camp_id_by_name
except Exception:
    get_camp_id_by_name = None


TABLE_MODEL_MAP = {
    "user": User,
    "camp": Camp,
    "user_type": UserType,
    "attendance_daily": AttendanceDaily,
    "session_activity_log": SessionActivityLog,
}

ALLOWED_OPS = {"eq", "in", "lt", "lte", "gt", "gte", "between"}


def _normalize_text(v: str) -> str:
    # camp_name 깨짐(머물머 물) 방어: 공백 제거 + 좌우 strip
    return v.strip().replace(" ", "")


def _resolve_token(value: Any, state: MessagingAgentState, ctx: Dict[str, Any]) -> Any:
    # 문자열 토큰 치환
    if isinstance(value, str):
        if value == "TODAY":
            ct = getattr(state, "current_time", None)
            if isinstance(ct, datetime):
                return ct.date()
            return datetime.now().date()

        if value == "$camp_id":
            return ctx.get("camp_id") or getattr(state, "camp_id", None)

        if value == "$target_user_ids":
            return ctx.get("target_user_ids") or getattr(state, "target_user_ids", None)

        # 일반 문자열은 정규화(특히 캠프명)
        return _normalize_text(value)

    # 리스트/튜플 내부 재귀
    if isinstance(value, list):
        return [_resolve_token(x, state, ctx) for x in value]
    if isinstance(value, tuple):
        return tuple(_resolve_token(x, state, ctx) for x in value)

    return value


def _build_filter(model, field: str, op: str, value: Any):
    if not hasattr(model, field):
        raise ValueError(f"Unknown field '{field}' for table '{model.__tablename__}'")

    col = getattr(model, field)

    if op == "eq":
        return col == value
    if op == "in":
        if not isinstance(value, list):
            raise ValueError(f"'in' op requires list value, got {type(value)}")
        return col.in_(value)
    if op == "lt":
        return col < value
    if op == "lte":
        return col <= value
    if op == "gt":
        return col > value
    if op == "gte":
        return col >= value
    if op == "between":
        if not (isinstance(value, list) and len(value) == 2):
            raise ValueError("'between' op requires [start, end]")
        return col.between(value[0], value[1])

    raise ValueError(f"Unsupported op '{op}'")


def _rows_to_dicts(rows: List[Any], fields: Optional[List[str]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in rows:
        d: Dict[str, Any] = {}
        if fields:
            for f in fields:
                if not hasattr(r, f):
                    raise ValueError(f"Row has no field '{f}'")
                d[f] = getattr(r, f)
        else:
            # fields 지정이 없으면 가능한 값만(내부키 제외)
            for k, v in r.__dict__.items():
                if k.startswith("_sa_"):
                    continue
                d[k] = v
        out.append(d)
    return out


def _ensure_state_results_container(state: MessagingAgentState):
    """
    MessagingAgentState가 extra=forbid이면 state.query_results 할당이 터질 수 있음.
    그 경우라도 실행은 계속하고, 결과는 로컬 딕트로만 유지한다.
    """
    if getattr(state, "query_results", None) is None:
        try:
            state.query_results = {}
        except Exception:
            # state에 필드가 없으면 그냥 무시(로컬로만 저장)
            return


def execute_query_plans_node(state: MessagingAgentState) -> MessagingAgentState:
    print("\n==============================")
    print("[NODE] execute_query_plans_node START")
    print("==============================")

    # 0) parsed 존재 확인
    if not getattr(state, "parsed", None):
        state.error = "execute_query_plans_node failed: state.parsed is None"
        print("[ERROR]", state.error)
        return state

    plans = getattr(state.parsed, "query_plans", None) or []
    if not isinstance(plans, list) or len(plans) == 0:
        print("[QUERY] No query_plans. Skip.")
        state.error = None
        return state

    # state에 query_results 필드가 있으면 생성
    _ensure_state_results_container(state)

    # 실행 컨텍스트(토큰 치환용)
    ctx: Dict[str, Any] = {
        "camp_id": getattr(state, "camp_id", None),
        "target_user_ids": getattr(state, "target_user_ids", None),
    }

    # 로컬 결과 저장소(상태에 못 쓰는 경우 대비)
    local_results: Dict[str, Any] = {}

    # DB 세션
    db_gen = get_db()
    db: Session = next(db_gen)

    def _save_result(key: str, value: Any):
        local_results[key] = value
        if getattr(state, "query_results", None) is not None:
            try:
                state.query_results[key] = value
            except Exception:
                pass

    try:
        for i, raw_plan in enumerate(plans):
            # pydantic model이면 dict로
            plan = raw_plan.model_dump() if hasattr(raw_plan, "model_dump") else raw_plan
            plan_id = plan.get("id") or f"plan_{i+1}"
            table = plan.get("table") or plan.get("db_table")
            fields = plan.get("fields", None)
            filters = plan.get("filters", []) or []
            limit = plan.get("limit", 200)
            save_as = plan.get("save_as") or plan_id

            if table not in TABLE_MODEL_MAP:
                # 모르는 테이블이면 해당 plan만 스킵하고 계속
                msg = f"[WARN] {plan_id}: unknown table='{table}' -> skip"
                print(msg)
                _save_result(save_as, {"error": msg, "rows": []})
                continue

            model = TABLE_MODEL_MAP[table]

            # 1) 필터식 구성
            exprs = []
            resolved_filters = []
            for f in filters:
                if hasattr(f, "model_dump"):
                    f = f.model_dump()

                field = f.get("field")
                op = f.get("op")
                value = f.get("value")

                if not field or not op:
                    raise ValueError(f"{plan_id}: filter missing field/op")
                if op not in ALLOWED_OPS:
                    raise ValueError(f"{plan_id}: op '{op}' not allowed")

                resolved_value = _resolve_token(value, state, ctx)
                resolved_filters.append((field, op, resolved_value))

                # camp_id 토큰이 None이면 "해당 plan 실행 불가" → plan만 skip
                if op == "eq" and field == "camp_id" and resolved_value is None:
                    msg = f"[SKIP] {plan_id}: camp_id is None, cannot run this plan"
                    print(msg)
                    _save_result(save_as, {"error": msg, "rows": []})
                    exprs = None
                    break

                exprs.append(_build_filter(model, field, op, resolved_value))

            if exprs is None:
                # skip 처리됨
                continue

            # 2) 조회 실행
            q = db.query(model)
            if exprs:
                q = q.filter(and_(*exprs))
            q = q.limit(min(int(limit or 200), 200))
            rows = q.all()
            dict_rows = _rows_to_dicts(rows, fields)

            # 3) camp 조회가 0건이면 "캠프명 정규화 재시도" (특별 처리)
            if table == "camp" and len(dict_rows) == 0:
                # 재시도: 필터의 name 값을 state.parsed.camp_name으로 강제
                # name 필터가 있는 케이스만
                parsed_camp = getattr(state.parsed, "camp_name", None)
                if parsed_camp:
                    normalized = _normalize_text(parsed_camp)
                    # name eq 필터가 있다면 대체해서 재쿼리
                    retry_exprs = []
                    for field, op, val in resolved_filters:
                        if field == "name" and op == "eq":
                            val = normalized
                        retry_exprs.append(_build_filter(model, field, op, val))

                    q2 = db.query(model).filter(and_(*retry_exprs)).limit(1)
                    rows2 = q2.all()
                    dict_rows = _rows_to_dicts(rows2, fields)

                # 그래도 0건이면 tool fallback(가능할 때)
                if len(dict_rows) == 0 and get_camp_id_by_name is not None and parsed_camp:
                    try:
                        cid = get_camp_id_by_name.invoke({"camp_name": _normalize_text(parsed_camp)})
                        dict_rows = [{"camp_id": cid}]
                    except Exception:
                        pass

            print(f"[QUERY] {plan_id} table={table} -> rows={len(dict_rows)} saved_as={save_as}")
            _save_result(save_as, dict_rows)

            # 4) save_as 기반 state/ctx 반영 (핵심)
            if save_as == "camp_id":
                if dict_rows and dict_rows[0].get("camp_id") is not None:
                    cid = dict_rows[0]["camp_id"]
                    state.camp_id = cid
                    ctx["camp_id"] = cid

            if save_as == "target_user_ids":
                user_ids = [r.get("user_id") for r in dict_rows if r.get("user_id") is not None]
                state.target_user_ids = user_ids
                ctx["target_user_ids"] = user_ids

        # 결과가 state에 못 들어갔을 수도 있으니 (필드 없을 경우) 최소 에러는 남겨두자
        state.error = None
        print("[NODE] execute_query_plans_node END")
        return state

    except Exception as e:
        print("[ERROR] execute_query_plans_node failed")
        print(e)

        # 그래프를 완전히 깨지지 않게: 에러 기록하고, 지금까지의 결과는 유지
        state.error = f"execute_query_plans_node failed: {e}"

        # query_results가 없으면 로컬이라도 남기기(있다면)
        if getattr(state, "query_results", None) is None:
            # state에 못 넣는 환경이라면 여기서는 어쩔 수 없음
            pass

        return state

    finally:
        try:
            db.close()
        except Exception:
            pass
        try:
            next(db_gen)
        except Exception:
            pass
