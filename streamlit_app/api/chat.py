# streamlit_app/api/curriculum.py
import os
import requests
from dotenv import load_dotenv

load_dotenv()

BACKEND_BASE_URL = os.getenv("BACKEND_BASE_URL")


def send_chat(user_input):
    url = f"{BACKEND_BASE_URL}/dispatch/send"
    resp = requests.post(
                    url,
                    json={"request_text": user_input, "user_id": 1},
                )
    return resp
