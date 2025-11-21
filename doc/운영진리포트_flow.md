```
flowchart TD
    U[리포트 생성 클릭] --> O[Orchestrator]

    subgraph LOGS[캠프 데이터]
        L1[챗봇 질문 로그]
        L2[출석 로그]
        L3[반 회의 로그]
    end

    O --> T1[지표 조회 Tool]
    O --> T2[출석 추이 조회 Tool]
    O --> T3[질문 예시 조회 Tool]

    L1 --> T1
    L2 --> T2
    L1 --> T3

    T1 --> O
    T2 --> O
    T3 --> O

    O --> S1[구간 스코어링 Agent]
    S1 --> O2[병목 후보 구간]

    O2 --> A1[병목 분석 Agent]
    A1 --> A2[영향 평가 Agent]
    A2 --> P1[액션 플래너 Agent]

    P1 --> R[최종 JSON 리포트]
    R --> UI[Streamlit UI]
```