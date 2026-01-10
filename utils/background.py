import asyncio
import logging
from const import game_array
from database.actions import db
import requests
import os
from utils.clue import clue_obj

logger = logging.getLogger(__name__)

URL_SERVICE = os.getenv("URL_SERVICE")
HASH = os.getenv("HASH")


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
            data = {
                "password": HASH,
                "game": game,
            }
            response = await asyncio.to_thread(requests.post, URL_SERVICE, json=data)
            setattr(clue_obj, f"clue_{game}", response)
            logger.info(f"Generated clue for {game}: {response.text}")
        await asyncio.sleep(86400)