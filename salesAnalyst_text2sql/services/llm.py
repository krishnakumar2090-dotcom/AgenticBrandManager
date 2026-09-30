import os
import requests
from dotenv import load_dotenv
from services.constants import LLM_API_URL as API_URL, MODEL_NAME

load_dotenv(override=True)

LLM_API_KEY = os.getenv("LLM_API_KEY")
headers = {"Content-Type": "application/json", "api-key": LLM_API_KEY}


def get_llm_response(prompt: str) -> str:
    try:
        resp = requests.post(
            API_URL,
            headers=headers,
            json={"model": MODEL_NAME, "input": prompt},
            timeout=90,
        )

        resp.raise_for_status()

        data = resp.json()

        return next(item for item in data["output"] if item["type"] == "message")[
            "content"
        ][0]["text"]

    except requests.RequestException as error:
        status_code = getattr(error.response, "status_code", "network error")
        response_text = getattr(error.response, "text", str(error))
        raise RuntimeError(f"LLM request failed ({status_code}): {response_text[:500]}")
