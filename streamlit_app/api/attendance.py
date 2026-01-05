# streamlit_app/api/attendance.py
import datetime
import os
import requests
from dotenv import load_dotenv

load_dotenv()

BACKEND_BASE_URL = os.environ.get("BACKEND_BASE_URL")

def get_attendance_report(camp_id, target_date):
    resp = requests.get(
        f"{BACKEND_BASE_URL}/attendance/report",
        params={"camp_id": camp_id, "target_date": target_date},
    )
    # resp.raise_for_status()
    return resp.json()

def generate_attendance_report(camp_id: int, target_date: datetime):
    payload = {
        "camp_id": camp_id,
        "target_date": target_date.isoformat(),  # "2025-01-10"
    }
    res = requests.post(
        f"{BACKEND_BASE_URL}/attendance/report/generate",
        json=payload, 
    )
    res.raise_for_status()
    return res.json()

def get_attendance_ruleset(camp_id: int):
    resp = requests.get(
        f"{BACKEND_BASE_URL}/attendance_ruleset/{camp_id}",
    )
    resp.raise_for_status()
    return resp.json()  # 없으면 None


def save_attendance_ruleset(camp_id: int, raw_rules_text: str, name: str = "출결 규칙"):
    payload = {
        "camp_id": camp_id,
        "name": name,
        "raw_rules_text": raw_rules_text,
    }
    resp = requests.post(
        f"{BACKEND_BASE_URL}/attendance_ruleset/generate",
        json=payload,
    )
    resp.raise_for_status()
    return resp.json()
