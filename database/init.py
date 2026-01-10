import logging

import asyncpg

logger = logging.getLogger(__name__)


class CreateDB:
    """
    Подключение и создание базы данных
    """

    def __init__(self):
        self.pool = None

    async def connect(self, dsn: str, min_size: int = 5, max_size: int = 20):
        self.pool = await asyncpg.create_pool(
            dsn=dsn,
            min_size=min_size,
            max_size=max_size,
            command_timeout=60,
            server_settings={
                "application_name": "spy_game_bot",
                "idle_in_transaction_session_timeout": "60000",
            },
        )
        logger.info("Connected to PostgreSQL")
        await self.init_db()

    async def init_db(self):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS rooms (
                    id VARCHAR(10) PRIMARY KEY,
                    creator_id BIGINT NOT NULL,
                    mode VARCHAR(20) DEFAULT 'clash',
                    word VARCHAR(100),
                    spy_id BIGINT,
                    card_url TEXT,
                    game_started BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP + INTERVAL '24 hours'
                )
            """)

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS players (
                    user_id BIGINT,
                    room_id VARCHAR(10),
                    role VARCHAR(20),
                    word VARCHAR(100),
                    card_url TEXT,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, room_id),
                    FOREIGN KEY (room_id) REFERENCES rooms(id) ON DELETE CASCADE
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_accounts (
                    user_id BIGINT PRIMARY KEY,
                    balance INTEGER DEFAULT 0,
                    hard_hints INTEGER DEFAULT 0,
                    medium_hints INTEGER DEFAULT 0,
                    easy_hints INTEGER DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)


db_init = CreateDB()
