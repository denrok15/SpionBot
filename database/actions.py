from typing import List, Optional
import asyncpg
from database.init import db_init

class ButtonCommand:
    def __init__(self, pool):
        self.pool = pool

    async def create_room(
        self, room_id: str, creator_id: int, mode: str = "clash"
    ) -> bool:
        async with self.pool.acquire() as conn:
            try:
                await conn.execute(
                    """
                    INSERT INTO rooms (id, creator_id, mode, expires_at)
                    VALUES ($1, $2, $3, CURRENT_TIMESTAMP + INTERVAL '24 hours')
                """,
                    room_id,
                    creator_id,
                    mode,
                )
                await self.add_player_to_room(creator_id, room_id)
                return True
            except asyncpg.UniqueViolationError:
                return False

    async def get_room(self, room_id: str) -> Optional[dict]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM rooms WHERE id = $1", room_id)
            return dict(row) if row else None

    async def update_room_game_state(
        self, room_id: str, word: str, spy_id: int, card_url: str = None
    ):
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE rooms 
                SET word = $1, spy_id = $2, card_url = $3, 
                    game_started = TRUE, updated_at = CURRENT_TIMESTAMP
                WHERE id = $4
            """,
                word,
                spy_id,
                card_url,
                room_id,
            )

    async def reset_room_game(self, room_id: str) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE rooms 
                SET word = NULL, spy_id = NULL, card_url = NULL,
                    game_started = FALSE, updated_at = CURRENT_TIMESTAMP
                WHERE id = $1
            """,
                room_id,
            )
            await conn.execute(
                """
                UPDATE players 
                SET role = NULL, word = NULL, card_url = NULL
                WHERE room_id = $1
            """,
                room_id,
            )

    async def delete_room(self, room_id: str) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute("DELETE FROM rooms WHERE id = $1", room_id)

    async def update_room_mode(self, room_id: str, mode: str) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE rooms 
                SET mode = $1, updated_at = CURRENT_TIMESTAMP
                WHERE id = $2
            """,
                mode,
                room_id,
            )

    async def add_player_to_room(self, user_id: int, room_id: str) -> bool:
        async with self.pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM players WHERE room_id = $1", room_id
            )
            if count >= 15:
                return False
            try:
                await conn.execute(
                    """
                    INSERT INTO players (user_id, room_id)
                    VALUES ($1, $2)
                    ON CONFLICT (user_id, room_id) DO NOTHING
                """,
                    user_id,
                    room_id,
                )
                return True
            except:
                return False

    async def remove_player_from_room(self, user_id: int, room_id: str) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM players WHERE user_id = $1 AND room_id = $2",
                user_id,
                room_id,
            )

    async def get_room_players(self, room_id: str) -> List[int]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT user_id FROM players WHERE room_id = $1 ORDER BY joined_at",
                room_id,
            )
            return [row["user_id"] for row in rows]

    async def get_player_data(self, user_id: int, room_id: str) -> Optional[dict]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM players WHERE user_id = $1 AND room_id = $2",
                user_id,
                room_id,
            )
            return dict(row) if row else None

    async def update_player_role(
        self,
        user_id: int,
        room_id: str,
        role: str,
        word: str = None,
        card_url: str = None,
    ):
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE players 
                SET role = $1, word = $2, card_url = $3
                WHERE user_id = $4 AND room_id = $5
            """,
                role,
                word,
                card_url,
                user_id,
                room_id,
            )

    async def get_user_room(self, user_id: int) -> Optional[str]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT room_id FROM players WHERE user_id = $1 LIMIT 1", user_id
            )
            return row["room_id"] if row else None

    async def get_room_creator(self, room_id: str) -> Optional[int]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT creator_id FROM rooms WHERE id = $1", room_id
            )
            return row["creator_id"] if row else None

    async def transfer_room_ownership(self, room_id: str, new_creator_id: int)->None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE rooms SET creator_id = $1 WHERE id = $2",
                new_creator_id,
                room_id,
            )

    async def cleanup_old_rooms(self)->None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM rooms WHERE expires_at < NOW() - INTERVAL '1 hour'"
            )

    async def get_all_rooms_stats(self) -> dict:
        async with self.pool.acquire() as conn:
            total_rooms = await conn.fetchval("SELECT COUNT(*) FROM rooms")
            active_rooms = await conn.fetchval(
                "SELECT COUNT(*) FROM rooms WHERE game_started = TRUE"
            )
            total_players = await conn.fetchval("SELECT COUNT(*) FROM players")
            return {
                "total_rooms": total_rooms,
                "active_rooms": active_rooms,
                "total_players": total_players,
            }

    async def get_cached_image(self, url: str) -> Optional[str]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT file_id FROM image_cache 
                WHERE url = $1 AND cached_at > CURRENT_TIMESTAMP - INTERVAL '7 days'
            """,
                url,
            )
            return row["file_id"] if row else None

    async def cache_image(self, url: str, file_id: str, mode: str):
        async with self.pool.acquire() as conn:
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

    async def cleanup_image_cache(self):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM image_cache WHERE cached_at < CURRENT_TIMESTAMP - INTERVAL '30 days'"
            )


db = ButtonCommand(db_init.pool)
