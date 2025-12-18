import asyncio
import logging

from database.actions import db
from utils.clue import clue_obj
from utils.llm import PROMPTS, ask_llm

logger = logging.getLogger(__name__)

async def periodic_cleanup()->None:
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

async def generate_clue()->None:
    while True:
        for prompt in PROMPTS:
            try:
                result = await ask_llm(prompt)
                setattr(clue_obj, f"clue_{prompt}", result)
                logger.info("Подсказки обновлены")
            except Exception as e:
                logger.error(f"Error in generate_clue: {e}")
            await asyncio.sleep(1800)
