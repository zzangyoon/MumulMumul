import json
from pathlib import Path
from typing import Dict, Any

_TENDENCY_JSON_PATH = (
    Path(__file__).resolve().parents[3] / "Storage" / "tendency_profiles.json"
)

_tendency_cache: Dict[str, Any] | None = None


def load_tendency_profiles() -> Dict[str, Any]:
    """
    성향 분석 JSON 로드 (단순 캐시)
    """
    global _tendency_cache

    if _tendency_cache is not None:
        return _tendency_cache

    with open(_TENDENCY_JSON_PATH, "r", encoding="utf-8") as f:
        _tendency_cache = json.load(f)

    return _tendency_cache

# 성향 분석 프로필 내용을 컨텍스트에 넣을 수 있는 형태로 변환
def get_tendency_profiles_context() -> Dict[str, Any]:
    tendency_data = load_tendency_profiles()
    tendency_profiles = tendency_data.get("profiles", {})

    # "profiles": {
    # "ANALYST": {
    #   "label": "🧭 분석가",
    #   "color": "초록 머물이",
    #   "core_trait": "계획 & 정확성",
    #   "description": "모든 일에 앞서 신중한 계획과 논리적 분석을 최우선으로 하며, 구조와 설계를 중시하는 성향입니다.",
    #   "strength_message": "논리적 설계 능력으로 팀의 방향을 제시합니다.",
    #   "caution_message": "완벽함을 추구하다 실행이 늦어질 수 있으니, 일정 내 실행 속도를 의식적으로 조절해 보세요.",
    #   "team_role": "팀의 초반 설계와 구조 정리, 그리고 최종 단계의 오류 검토를 담당하여 안정성을 높입니다.",
    #   "dm_tone_hint": "논리적 근거 제시, 명확한 기준 설명, 감정 과잉 표현 지양"
    # }}
    tendency_context = ""
    tendency_context += f"[성향 분석 개요]\n{tendency_data.get('intro', '')}\n\n"
    tendency_context += f"[성향별 프로필]\n {len(tendency_profiles)}가지 성향 유형이 있습니다.\n\n"
    for profile_key, profile_info in tendency_profiles.items():
        context = f"""
            성향 유형: ({profile_info.get('label', '')}
            핵심 특성: {profile_info.get('core_trait', '')}
            설명: {profile_info.get('description', '')}
            강점: {profile_info.get('strength_message', '')}
            주의할 점: {profile_info.get('caution_message', '')}
            팀 내 역할: {profile_info.get('team_role', '')}
            DM 톤 힌트: {profile_info.get('dm_tone_hint', '')}
        """
        tendency_context += context + "\n"
    return tendency_context