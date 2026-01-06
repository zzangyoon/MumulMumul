from datetime import datetime
import os

import requests

BACKEND_BASE_URL = os.getenv("BACKEND_BASE_URL")
def _get_backend_base_url() -> str:
    base = os.getenv("BACKEND_BASE_URL")
    if not base:
        base = "http://localhost:8020"
    return base.rstrip("/")  # 끝 / 제거해서 // 방지

def fetch_feedback_report(camp_id: str, week_index: int) -> dict | None:
    """백엔드에서 특정 캠프와 주차의 피드백 리포트를 조회합니다.
        /report/{camp_id}/{week_index}
    """
    base = _get_backend_base_url()
    url = f"{base}/feedback/report/{camp_id}/{week_index}"
    resp = requests.get(url)
    if resp == None or resp.status_code == 404:
        return None
    return resp.json()

def create_feedback_report(camp_id: str, week_index: int) -> dict:
    """백엔드에서 특정 캠프와 주차의 피드백 리포트를 생성합니다.
        /report/{camp_id}/{week_index}/build
    """
    base = _get_backend_base_url()
    url = f"{base}/feedback/report/{camp_id}/{week_index}/build"
    resp = requests.post(url)
    resp.raise_for_status()
    return resp.json()