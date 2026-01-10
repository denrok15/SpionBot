import asyncio
import logging
from const import game_array
from database.actions import db
from database.redis import set_clue_hero
import os
import requests
logger = logging.getLogger(__name__)

HASH = os.getenv("HASH")
URL = os.getenv("URL")
async def periodic_cleanup() -> None:
    """Фоновая задача для очистки старых данных"""
    while True:
        try:
            await db.cleanup_old_rooms()
            await db.cleanup_image_cache()
            stats = await db.get_all_rooms_stats()
            logger.info(f"Cleanup completed. Stats: {stats}")
        except Exception as e:
            logger.error(f"Error in periodic cleanup: {e}")
        await asyncio.sleep(1800)


async def generate_clue() -> None:
    await asyncio.sleep(5)
    while True:
        for game in game_array:
            response = take_clue_serves(game)
            for hero in response["result"]:
                set_clue_hero(hero,response["result"][hero])
        await asyncio.sleep(86400)
async def update_connect() -> None:
    while True:
        headers = {
            "accept": "application/json",
            "Content-Type": "application/json"
        }
        response = requests.get(URL, headers=headers)
        await asyncio.sleep(60)
def take_clue_serves(game: str) -> dict:
    logger.info(f"Getting clue serves for {game}")
    payload = {"password": HASH, "game": game}
    headers = {"accept": "application/json", "Content-Type": "application/json"}
    response = requests.post(URL, json=payload, headers=headers)
    return response.json()