import asyncio

from database.actions import db
from utils.decorators import logger


async def periodic_cleanup():
    """Фоновая задача для очистки старых данных"""
    while True:
        try:
            await db.cleanup_old_rooms()
            await db.cleanup_image_cache()

            stats = await db.get_all_rooms_stats()
            logger.info(f"Cleanup completed. Stats: {stats}")

        except Exception as e:
            logger.error(f"Error in periodic cleanup: {e}")

        await asyncio.sleep(1800)  # Каждые 30 минут
