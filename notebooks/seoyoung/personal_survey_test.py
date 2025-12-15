import sys
from pathlib import Path


CURRENT_FILE = Path(__file__).resolve()
ROOT_DIR = CURRENT_FILE.parents[2]   # .../MumulMumul
sys.path.append(str(ROOT_DIR))

import random
import json
from collections import Counter
from app.config import PERSONAL_SURVEY_CONFIG_PATH

def load_trait_config(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

# -------------------------
# 1) 관계 정의 (personaWeights 반영 버전)
# -------------------------
config = json.load(open(PERSONAL_SURVEY_CONFIG_PATH, encoding="utf-8"))
questions = config["questions"]

# 타입 우선순위 (동점일 때 적용)
priority_order = ["analyst", "pillar", "balancer", "supporter", "doer"]

def calculate_personality_type(result, config):
    questions = config["questions"]

    persona_scores = {
        "analyst": 0,
        "doer": 0,
        "balancer": 0,
        "supporter": 0,
        "pillar": 0,
    }

    # 1) 기본 점수 누적
    for i, user_choice in enumerate(result):
        question = questions[i]
        choice = question["choices"][user_choice]
        weights = choice.get("personaWeights", {})
        for persona, w in weights.items():
            if persona in persona_scores:
                persona_scores[persona] += w

    # 2) 타입별 보정 계수 적용 (analyst 너프, 나머지 살짝 버프)
    adjust_factors = {
        "analyst":   0.60,   # 분석가 살짝 너프
        "doer":      0.65,   # 실행가 살짝 버프
        "balancer":  0.67,   # 밸런서 약간 버프
        "supporter": 0.63,   # 협력가 약간 버프
        "pillar":    0.69    # 원칙주의자 버프
    }

    for persona, factor in adjust_factors.items():
        persona_scores[persona] *= factor

    # 3) 최댓값 기준 타입 선택 (priority는 그대로)
    priority_order = ["pillar", "doer", "balancer", "supporter", "analyst"]

    max_score = max(persona_scores.values())
    candidates = [p for p, s in persona_scores.items() if s == max_score]

    for p in priority_order:
        if p in candidates:
            type_code = p
            break

    return type_code, persona_scores


# -------------------------
# 2) 시뮬레이션 실행
# -------------------------
N = 10000
counter = Counter()

results = {key: [] for key in priority_order}

for _ in range(N):
    # 각 문항에서 선택지 랜덤 선택
    result = [random.choice([0, 1]) for _ in range(len(questions))]
    persona, persona_scores = calculate_personality_type(result, load_trait_config(PERSONAL_SURVEY_CONFIG_PATH))
    counter[persona] += 1

    results[persona].append(result)

# 각 키별로 상위 10개 결과 출력
for key in priority_order:
    print(f"=== {key} 상위 10개 결과 ===")
    for res in results[key][:10]:
        print(res)
    print()

# -------------------------
# 3) 결과 출력
# -------------------------
print("=== 캐릭터 비율 ===")
for persona, count in counter.items():
    print(f"{persona}: {count / N * 100:.2f}%")