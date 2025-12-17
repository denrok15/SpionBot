import logging
from typing import Dict, Optional

import aiohttp

logger = logging.getLogger(__name__)


class ImageCache:
    def __init__(self, db_pool):
        self.db_pool = db_pool
        self.memory_cache: Dict[str, str] = {}
        self.session: Optional[aiohttp.ClientSession] = None

    async def get_cached_image_id(self, url: str, mode: str) -> Optional[str]:
        """Получение file_id изображения из кэша"""
        if url in self.memory_cache:
            return self.memory_cache[url]

        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT file_id FROM image_cache 
                WHERE url = $1 AND cached_at > CURRENT_TIMESTAMP - INTERVAL '7 days'
            """,
                url,
            )

            if row:
                file_id = row["file_id"]
                self.memory_cache[url] = file_id
                return file_id

        return None

    async def cache_image_id(self, url: str, file_id: str, mode: str):
        """Кэширование file_id изображения"""
        self.memory_cache[url] = file_id

        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO image_cache (url, file_id, mode, cached_at)
                VALUES ($1, $2, $3, CURRENT_TIMESTAMP)
                ON CONFLICT (url) DO UPDATE 
                SET file_id = EXCLUDED.file_id, cached_at = EXCLUDED.cached_at
            """,
                url,
                file_id,
                mode,
            )

    async def cleanup_cache(self):
        """Очистка старых записей в кэше"""
        async with self.db_pool.acquire() as conn:
            await conn.execute("""
                DELETE FROM image_cache 
                WHERE cached_at < CURRENT_TIMESTAMP - INTERVAL '30 days'
            """)

        if len(self.memory_cache) > 1000:
            self.memory_cache.clear()
