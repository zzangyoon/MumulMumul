from datetime import datetime
import os

import requests

BACKEND_BASE_URL = os.getenv("BACKEND_BASE_URL")

def fetch_feedback_report(camp_id: str, week_index: int) -> dict | None:
    """백엔드에서 특정 캠프와 주차의 피드백 리포트를 조회합니다.
        /report/{camp_id}/{week_index}
    """
    url = f"{BACKEND_BASE_URL}/feedback/report/{camp_id}/{week_index}"
    resp = requests.get(url)
    if resp == None or resp.status_code == 404:
        return None
    return resp.json()

def create_feedback_report(camp_id: str, week_index: int) -> dict:
    """백엔드에서 특정 캠프와 주차의 피드백 리포트를 생성합니다.
        /report/{camp_id}/{week_index}/build
    """
    url = f"{BACKEND_BASE_URL}/feedback/report/{camp_id}/{week_index}/build"
    resp = requests.post(url)
    resp.raise_for_status()
    return resp.json()