import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
from datetime import datetime, timedelta

# ============================================
# 0. 더미 데이터 & 유틸 함수 (상단에 몰아두기)
# ============================================

@st.cache_data
def make_dummy_feedback():
    np.random.seed(42)

    camps = [
        {"camp_id": 1, "camp_name": "데이터 분석 1반"},
        {"camp_id": 2, "camp_name": "프론트엔드 1반"},
    ]

    users = [101, 102, 103, 104, 105]
    categories = [
        "팀 갈등",
        "일정 압박",
        "과제 난이도",
        "운영/행정",
        "피로/번아웃",
    ]
    sub_clusters = {
        "팀 갈등": ["역할 분배 갈등", "팀장-팀원 의사소통 문제"],
        "일정 압박": ["데드라인 부담", "야근/추가 작업 요구"],
        "과제 난이도": ["난이도 과도", "요구사항 불명확"],
        "운영/행정": ["공지/소통 부족", "운영 정책 불만"],
        "피로/번아웃": ["체력적 피로", "동기 저하"],
    }

    types = ["고민", "건의"]
    severities = ["low", "medium", "high"]

    rows = []
    base_date = datetime(2025, 11, 1)

    for camp in camps:
        for week in range(1, 7):  # Week 1~6
            for _ in range(np.random.randint(8, 18)):  # 주차당 글 수
                cat = np.random.choice(categories)
                sub = np.random.choice(sub_clusters[cat])
                t = np.random.choice(types, p=[0.7, 0.3])

                severity = np.random.choice(
                    severities,
                    p=[0.5, 0.3, 0.2],  # high는 적게
                )
                is_toxic = bool(np.random.rand() < 0.25)  # 25% 정도 토식

                day_offset = (week - 1) * 7 + np.random.randint(0, 7)
                created_at = base_date + timedelta(days=int(day_offset))
                hour = np.random.choice([10, 14, 20, 22])
                created_at = created_at.replace(hour=hour, minute=0)

                user_id = np.random.choice(users)

                text = f"[더미] {cat} / {sub} 관련 {t} 글입니다. (user {user_id}, week {week})"
                summary = f"{cat} – {sub}에 대한 {t} 내용 요약."

                rows.append(
                    {
                        "camp_id": camp["camp_id"],
                        "camp_name": camp["camp_name"],
                        "week": week,
                        "created_at": created_at,
                        "category": cat,
                        "sub_cluster": sub,
                        "type": t,  # 고민 / 건의
                        "is_toxic": is_toxic,
                        "severity": severity,  # low / medium / high
                        "user_id": user_id,
                        "text": text,
                        "summary": summary,
                    }
                )

    df = pd.DataFrame(rows)
    return camps, df


def classify_severity_level(count: int) -> str:
    """반복 이슈 규모에 따른 등급 나누기."""
    if count >= 10:
        return "high"
    elif count >= 5:
        return "medium"
    else:
        return "low"


def build_repeat_issues(upto_df: pd.DataFrame):
    """
    Week 1 ~ 선택 주차까지의 데이터를 바탕으로
    '반복 이슈' 후보를 클러스터 단위로 생성하는 더미 로직.
    실제에선 유사도 클러스터링 + LLM 요약으로 대체 예정.
    """
    if upto_df.empty:
        return []

    cluster_stats = (
        upto_df.groupby(["category", "sub_cluster"])
        .agg(
            count=("text", "count"),
            weeks=("week", lambda x: sorted(set(x))),
        )
        .reset_index()
    )

    issues = []
    for _, row in cluster_stats.iterrows():
        weeks = row["weeks"]
        count = int(row["count"])

        # 2개 이상 주차에서 등장하거나, 전체 4건 이상이면 반복 이슈로 간주 (더미 룰)
        if len(weeks) >= 2 or count >= 4:
            label = f"{row['category']} – {row['sub_cluster']}"
            severity = classify_severity_level(count)

            summary = (
                f"Week {', '.join(map(str, weeks))}에서 총 {count}건 언급된 이슈로, "
                f"'{row['category']}' 중 '{row['sub_cluster']}'에 대한 불만/고민이 반복되고 있음."
            )
            action_hint = (
                f"해당 이슈에 대해 공지/정책/보완 세션을 한 번 명확히 정리해 공유하고, "
                f"추가 피드백을 받을 수 있는 창구(예: 1:1 폼, 익명 설문)를 열어두는 것이 좋음."
            )

            issues.append(
                {
                    "label": label,
                    "count": count,
                    "weeks": weeks,
                    "severity": severity,
                    "summary": summary,
                    "action_hint": action_hint,
                }
            )

    # count 기준 내림차순 정렬
    issues = sorted(issues, key=lambda x: x["count"], reverse=True)
    return issues


def build_ops_actions(current_df: pd.DataFrame):
    """
    이번 주 데이터를 기반으로 운영진 우선 액션 Top 3를 만드는 간단한 더미 로직.
    실제에선 LLM + 규칙 기반으로 대체 예정.
    """
    actions = []

    if current_df.empty:
        return actions

    # 1) 카테고리별 글 수
    cat_count = current_df["category"].value_counts()

    # 액션 1: 가장 많이 나온 카테고리 보강
    if not cat_count.empty:
        top_cat = cat_count.index[0]
        top_cnt = int(cat_count.iloc[0])
        actions.append(
            {
                "title": f"1. '{top_cat}' 관련 집중 케어",
                "target": "해당 이슈를 자주 언급한 수강생 + 전체 공지",
                "reason": f"이번 주 '{top_cat}' 관련 글이 {top_cnt}건으로, 전체 이슈 중 가장 높은 비중을 차지함.",
                "todo": (
                    f"해당 이슈에 대한 FAQ/가이드 문서를 간단히 정리하여 공지하고, "
                    f"관계된 수강생에게는 1:1 또는 소규모 그룹으로 추가 설명/조율 세션을 제공."
                ),
            }
        )

    # 2) 토식 글이 많은 경우: 채널/멘토 운영 룰
    toxic_cnt = int(current_df["is_toxic"].sum())
    if toxic_cnt > 0:
        actions.append(
            {
                "title": "2. 감정 격앙/토식 글 대응 프로토콜 정비",
                "target": "운영진·멘토 전체",
                "reason": f"이번 주 토식 플래그가 찍힌 글이 총 {toxic_cnt}건 발생함.",
                "todo": (
                    "토식/격앙된 표현이 감지되었을 때, "
                    "① 문제 상황 사실 확인 → ② 1차 진정/공감 메시지 → ③ 필요시 개별 상담으로 전환하는 "
                    "3단계 대응 프로세스를 간단히 문서화하여 공유."
                ),
            }
        )

    # 3) 특정 시간대에 글이 몰리면, 그 타임에 대응 리소스 배치
    tmp = current_df.copy()
    tmp["hour"] = tmp["created_at"].dt.hour
    hour_stats = (
        tmp.groupby("hour")
        .size()
        .reset_index(name="cnt")
        .sort_values("cnt", ascending=False)
    )
    if not hour_stats.empty:
        peak_hour = int(hour_stats.iloc[0]["hour"])
        peak_cnt = int(hour_stats.iloc[0]["cnt"])
        actions.append(
            {
                "title": "3. 피크 시간대 채널 모니터링 강화",
                "target": "멘토/튜터 배치 담당자",
                "reason": f"{peak_hour}시에 글이 {peak_cnt}건 집중되어 올라오는 패턴이 보임.",
                "todo": (
                    f"{peak_hour}시 전후 1~2시간 동안 멘토/운영진이 채널을 우선적으로 체크하고, "
                    "해당 시간대에 올라오는 고민/건의는 12시간 이내 1차 답변을 달도록 SLA를 설정."
                ),
            }
        )

    # 3개까지만 사용
    return actions[:3]


def build_weekly_summary(current_df: pd.DataFrame):
    if current_df.empty:
        return {
            "mood_summary": "이번 주에는 등록된 글이 거의 없어, 전반적인 분위기는 조용한 편입니다.",
            "issues": [],
        }

    total = len(current_df)
    toxic = int(current_df["is_toxic"].sum())

    # ✅ 카테고리 기준 Top3 (더 안전한 버전)
    cat_stats = (
        current_df["category"]
        .value_counts()
        .reset_index(name="count")      # count 컬럼 명시적으로 생성
        .rename(columns={"index": "category"})
    )
    # 이 시점에서 columns = ["category", "count"]
    # count는 이미 숫자지만, 혹시 몰라 한 번 더 강제해도 됨
    cat_stats["count"] = pd.to_numeric(cat_stats["count"], errors="coerce")

    issues = []
    for _, row in cat_stats.head(3).iterrows():
        cnt = int(row["count"])
        ratio = cnt / total if total > 0 else 0
        issues.append(
            {
                "label": row["category"],
                "count": cnt,
                "ratio": ratio,
                "comment": f"전체 글의 약 {ratio*100:.1f}%가 '{row['category']}' 관련 이슈입니다.",
            }
        )

    if toxic == 0:
        mood = "전반적으로 분위기는 안정적이며, 갈등/불만보다는 단순 건의나 피드백 위주의 글이 많습니다."
    elif toxic / total < 0.2:
        mood = "일부 갈등/불만 글이 있지만, 아직은 관리 가능한 수준이며 조기 케어로 분위기 개선이 가능합니다."
    else:
        mood = "갈등/불만, 감정이 격한 글 비율이 높아 전체적으로 긴장된 분위기입니다. 빠른介入이 필요합니다."

    return {
        "mood_summary": mood,
        "issues": issues,
    }


# ============================================
# 1. 페이지 기본 설정
# ============================================
st.set_page_config(layout="wide")
st.title("🌲 속닥숲 리포트")

camps, df_all = make_dummy_feedback()

# ============================================
# 2. 사이드바 필터
# ============================================
st.sidebar.header("필터 설정")

camp_name_to_id = {c["camp_name"]: c["camp_id"] for c in camps}
camp_name = st.sidebar.selectbox("캠프 선택", list(camp_name_to_id.keys()))
camp_id = camp_name_to_id[camp_name]

weeks = [f"Week {i}" for i in range(1, 7)]
selected_week_label = st.sidebar.selectbox("주차 선택 (분석 기준 주차)", weeks)
selected_week = int(selected_week_label.split()[1])

# 이 캠프의 전체 데이터
camp_df = df_all[df_all["camp_id"] == camp_id].copy()

# 이번 주 데이터
current_df = camp_df[camp_df["week"] == selected_week].copy()

# Week 1 ~ 선택 주차까지 데이터
upto_df = camp_df[camp_df["week"] <= selected_week].copy()

if current_df.empty:
    st.warning("해당 캠프/주차에 대한 더미 데이터가 없습니다. 필터를 바꿔보세요.")
    st.stop()

# =========================================================
# 이번 주 리포트
# =========================================================
st.subheader(f"📊 {camp_name} / Week {selected_week} 리포트")

# -----------------------------
# (1) 상단 KPI 카드 & 워드클라우드
# -----------------------------
col_wc, col_summary = st.columns([1.2, 1])

# 왼쪽: 워드클라우드
with col_wc:
    st.markdown("#### 🔤 키워드 워드클라우드")
    placeholder_url = "https://via.placeholder.com/640x320?text=WordCloud+Demo"
    st.image(placeholder_url, caption="(데모) 이번 주 주요 키워드 워드클라우드")

# 오른쪽: 핵심 요약 3종
with col_summary:        
    total_posts = len(current_df)
    toxic_posts = int(current_df["is_toxic"].sum())
    toxic_ratio = toxic_posts / total_posts if total_posts > 0 else 0.0

    st.metric("전체 글 수 (이번 주)", f"{total_posts}건")
    st.metric("위험 글 수", f"{toxic_posts}건")
    st.metric("부정 글 비율", f"{toxic_ratio*100:.1f}%")

st.markdown("---")

# -----------------------------
# (2) 이번 주 상태 요약 + 주요 이슈
# -----------------------------
st.markdown("### 🧭 이번 주 상태 요약")

weekly_info = build_weekly_summary(current_df)
st.info(weekly_info["mood_summary"])

issues = weekly_info["issues"]
if issues:
    st.markdown("#### 🔍 주요 이슈 Top 3")
    cols = st.columns(len(issues))
    for idx, issue in enumerate(issues):
        with cols[idx]:
            with st.container(border=True):
                st.markdown(f"**{issue['label']}**")
                st.markdown(f"- 글 수: {issue['count']}건")
                st.markdown(f"- 비중: {issue['ratio']*100:.1f}%")
                st.caption(issue["comment"])
else:
    st.write("이번 주에는 두드러지는 이슈가 많지 않습니다.")

st.markdown("---")

# -----------------------------
# (3) 매우 위험한 글 리스트
# -----------------------------
st.markdown("#### 🚨 주요 위험 글")

risky_df = current_df[
(current_df["severity"] == "high") | (current_df["is_toxic"])
].copy()

if risky_df.empty:
    st.info("이번 주에는 고위험 글이 탐지되지 않았습니다.")
else:
    # 중요도 정렬: severity(high 우선) → is_toxic(True 우선) → 최신순
    severity_rank = {"high": 0, "medium": 1, "low": 2}
    risky_df["severity_rank"] = risky_df["severity"].map(severity_rank).fillna(2)

    risky_df = risky_df.sort_values(
        ["severity_rank", "is_toxic", "created_at"],
        ascending=[True, False, False],
    )

    # 상위 N개만 바로 보여주고 나머지는 토글로
    top_n = 2
    top_df = risky_df.head(top_n)
    rest_df = risky_df.iloc[top_n:]

def render_risky_row(r):
    level_label = "CRITICAL" if r["severity"] == "high" else "HIGH"
    header = (
        f"[{level_label}] Week {int(r['week'])} / "
        f"user {r['user_id']} / {r['created_at']:%Y-%m-%d %H:%M}"
        f"\n\n {r['summary']}"
    )

    # 헤더
    st.error(f"{header}")

    # CRITICAL인 경우: 헤더 바로 다음 줄에 요약 강조
    if r["severity"] == "high":
        st.markdown(f"**요약:** {r['summary']}")

    # 카테고리/클러스터 뱃지
    badge_html = f"""
    <div style="margin:4px 0 8px 0;">
        <span style="
            background-color:#eeeeee;
            border-radius:999px;
            padding:2px 8px;
            margin-right:4px;
            font-size:0.8rem;
        ">
        📂 {r['category']}
        </span>
        <span style="
            background-color:#f5f5f5;
            border-radius:999px;
            padding:2px 8px;
            font-size:0.8rem;
        ">
        🔎 {r['sub_cluster']}
        </span>
    </div>
    """
    st.markdown(badge_html, unsafe_allow_html=True)

    # HIGH(또는 그 외)인 경우: 여기서 요약 표기
    if r["severity"] != "high":
        st.markdown(f"- 요약: {r['summary']}")

    st.markdown(f"- (원문) {r['text']}")
    st.markdown("")

# 상위 2개는 그리드(2열)로 보여주기
cols = st.columns(2)
for idx, (_, row) in enumerate(top_df.iterrows()):
    with cols[idx % 2]:
        with st.container(border=True):
            render_risky_row(row)

# 나머지는 토글로 숨기기
if not rest_df.empty:
    with st.expander(f"나머지 위험 글 {len(rest_df)}개 더 보기"):
        for _, row in rest_df.iterrows():
            with st.container(border=True):
                render_risky_row(row)

st.markdown("---")

# -----------------------------
# (4) 운영진 우선 액션 Top 3
# -----------------------------
st.markdown("### 🏃 운영진 우선 액션 Top 3")

ops_actions = build_ops_actions(current_df)
if ops_actions:
    cols = st.columns(len(ops_actions))
    for idx, action in enumerate(ops_actions):
        with cols[idx]:
            with st.container(border=True):
                st.markdown(f"#### {action['title']}")
                st.markdown(f"- **대상**: {action['target']}")
                st.markdown(f"- **근거**: {action['reason']}")
                st.markdown("**이번 주 실행 액션**")
                st.markdown(action["todo"])
else:
    st.info("이번 주 기준으로 제안할 액션이 없습니다.")
