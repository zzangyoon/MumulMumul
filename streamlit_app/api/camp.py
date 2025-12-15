# streamlit_app/api/curriculum.py
import os
import requests


BACKEND_BASE_URL = os.getenv("BACKEND_BASE_URL", "http://localhost:8020")


def fetch_camps():
    """
    백엔드 /camps 에서 캠프(반) 리스트 가져오기
    return 예시:
    [
        {"camp_id": 1, "name": "프론트엔드 1반"},
        {"camp_id": 2, "name": "백엔드 1반"},
        ...
    ]
    """
    url = f"{BACKEND_BASE_URL}/camps/"
    res = requests.get(url)
    return res.json()
