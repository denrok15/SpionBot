import logging
import os

import requests
from dotenv import load_dotenv
logger = logging.getLogger(__name__)
load_dotenv()

API_KEY_LLM = os.getenv("API_KEY_LLM")
URL_LLM = os.getenv("URL_LLM")


async def ask_llm(promt: str) -> str:
    headers = {
        "Authorization": f"Bearer {API_KEY_LLM}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "openai/gpt-4o-mini",
        "messages": [
            {"role": "system", "content": "Ты точный генератор игровых подсказок."},
            {"role": "user", "content": promt},
        ],
        "temperature": 0.7,
    }
    response = requests.post(URL_LLM, headers=headers, json=payload)
    response.raise_for_status()
    logger.info("получен ответ от нейросети")
    return response.json()["choices"][0]["message"]["content"]
