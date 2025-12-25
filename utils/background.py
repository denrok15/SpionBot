import asyncio
import logging

from const import PROMPTS, game_array
from database.actions import db
from utils.clue import clue_obj
from utils.llm import ask_llm

logger = logging.getLogger(__name__)

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
    await asyncio.sleep(1800)
    while True:
        for game in PROMPTS:
            for Heroname in game_array[game]:
                try:
                    result = ask_llm(
                        PROMPTS[game].replace("{Heroname}", Heroname)
                    )
                    getattr(clue_obj, f"clue_{game}")[Heroname] = result[Heroname]
                    logger.info(f"Generated clue: {result}")
                except Exception as e:
                    logger.error(f"Error in generate_clue: {e}")
            logger.info(f"Подсказки для {game} обновлены")
        await asyncio.sleep(1800)
