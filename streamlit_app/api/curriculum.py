# streamlit_app/api/curriculum.py
import os
import requests
from dotenv import load_dotenv

load_dotenv()

BACKEND_BASE_URL = os.getenv("BACKEND_BASE_URL")


def fetch_curriculum_report(camp_id: int, week_index: str):
    """
    백엔드 /curriculum/report 에 리포트 요청
    """
    url = f"{BACKEND_BASE_URL}/curriculum/report"
    params = {"camp_id": camp_id, "week_index": week_index}
    resp = requests.get(url, params=params)
    if resp is None:
        return None
    return resp.json()

def create_curriculum_report(camp_id: int, week_index: str):
    """
    백엔드 /curriculum/newReport 에 리포트 요청
    """
    url = f"{BACKEND_BASE_URL}/curriculum/newReport"
    params = {"camp_id": camp_id, "week_index": week_index}
    resp = requests.get(url, params=params)
    return resp.json()


def fetch_curriculum_config(camp_id: int):
    resp = requests.get(f"{BACKEND_BASE_URL}/curriculum/config/{camp_id}")
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def save_curriculum_config(camp_id: int, weeks: list[dict]):
    payload = {"weeks": weeks}
    resp = requests.post(f"{BACKEND_BASE_URL}/curriculum/config/{camp_id}", json=payload)
    resp.raise_for_status()
    return resp.json()

def analyze_curriculum_text(camp_id: int, raw_text: str):
    payload = {"raw_text": raw_text}
    resp = requests.post(f"{BACKEND_BASE_URL}/curriculum/analyze/{camp_id}", json=payload)
    resp.raise_for_status()
    return resp.json()