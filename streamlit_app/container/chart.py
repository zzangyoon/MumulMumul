import pandas as pd
import altair as alt
import streamlit as st
from wordcloud import WordCloud
import matplotlib.pyplot as plt

def make_ratio_gauge(
    data,
    label_col="level",
    count_col="count",
    bar_label="비율",
    color_map=None,
    font_size=13,
):
    """
    data: list[dict] 또는 pd.DataFrame
        예: [{"level": "위험", "count": 5}, {"level": "주의", "count": 10}, ...]
    label_col: 라벨 컬럼 이름 (기본: "level")
    count_col: 개수 컬럼 이름 (기본: "count")
    bar_label: 한 줄 게이지에 붙일 이름 (y축용)
    color_map: {라벨: 색상(hex)} 형태 딕셔너리
    """

    # data → DataFrame으로 통일
    if isinstance(data, pd.DataFrame):
        df = data.copy()
    else:
        df = pd.DataFrame(data)

    if df.empty:
        return None

    total = df[count_col].sum()
    if total == 0:
        return None

    # 한 줄 게이지용 dummy 축
    df["bar"] = bar_label

    # 비율 및 중앙 위치 계산
    # TODO: 만약 비율이 너무 작을 경우 글자 겹침 > 숫자는 제대로 표시하지만 길이를 임의 조절
    df["pct"] = df[count_col] / total
    df["cum_pct"] = df["pct"].cumsum()
    df["label_x"] = df["cum_pct"] - df["pct"] / 2

    # "위험 (5건)" 이런 형태 라벨
    # 만약 비율이 0%인 항목이 있으면 표시 안 함
    df["label_with_count"] = df.apply(
        lambda r: f"{r[label_col]} ({int(r[count_col]/total*100)}%)" if r["pct"] > 0 else "",
        axis=1,
    )

    # 색상 스케일
    if color_map is not None:
        domain = list(color_map.keys())
        range_ = [color_map[k] for k in domain]
        color_encoding = alt.Color(
            f"{label_col}:N",
            title=None,
            scale=alt.Scale(domain=domain, range=range_),
        )
    else:
        color_encoding = alt.Color(f"{label_col}:N", title=None)

    base = alt.Chart(df)

    bar = (
        base
        .mark_bar()
        .encode(
            x=alt.X(
                "pct:Q",
                stack="zero",
                title=None,
                scale=alt.Scale(domain=[0, 1]),
                axis=None
            ),
            y=alt.Y("bar:N", axis=None),
            color=color_encoding,
            tooltip=[label_col, count_col],
        )
        .properties(height=80)
    )

    text = (
        base
        .mark_text(color="white", fontSize=font_size, fontWeight="bold")
        .encode(
            x=alt.X(
                "label_x:Q",
                title=None,
                scale=alt.Scale(domain=[0, 1]),
            ),
            y=alt.Y("bar:N", axis=None),
            text="label_with_count:N",
        )
    )

    return bar + text

stop = ["머물머물", "캠프", "학생", "수업", "과제", "챗봇", "좋겠어요", "있으면", "같아요", "해주세요", "합니다", "하는", "하는게", "해주세요", "해주세요", "입니다", "입니다", "같은", "같은게", "싶어요", "같다", "하다", "입니다", "입니다", "에서", "그리고", "하지만", "것이", "것을", "수가", "수가", "입니다", "입니다", "있다"]

def draw_wordcloud(words: list[str], width=800, height=800):
    """
    words: 키워드 리스트 (['공지', '과제', '멘붕', ...])
    """

    if not words:
        st.info("표시할 키워드가 없습니다.")
        return

    # 단어 빈도 계산
    freq = {}
    for w in words:
        w = str(w).strip()
        if w and (w not in stop):
            freq[w] = freq.get(w, 0) + 1

    wc = WordCloud(
        width=width,
        height=height,
        background_color="white",
        font_path="C:/Windows/Fonts/malgun.ttf",
        max_words=200,
        colormap="summer",
        prefer_horizontal=0.9,
        stopwords=stop,
    ).generate_from_frequencies(freq)

    fig, ax = plt.subplots(figsize=(width / 100, height / 100))
    ax.imshow(wc, interpolation="bilinear")
    ax.axis("off")

    st.pyplot(fig)