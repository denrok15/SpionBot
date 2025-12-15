import asyncpg
import asyncio
from datetime import datetime, timedelta
import logging
from typing import Dict, List, Optional, Tuple
import json

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.pool = None
    
    async def connect(self, dsn: str, min_size: int = 5, max_size: int = 20):
        """Подключение к PostgreSQL"""
        self.pool = await asyncpg.create_pool(
            dsn=dsn,
            min_size=min_size,
            max_size=max_size,
            command_timeout=60,
            server_settings={
                'application_name': 'spy_game_bot',
                'idle_in_transaction_session_timeout': '60000'
            }
        )
        logger.info("Connected to PostgreSQL")
        await self.init_db()
    
    async def init_db(self):
        """Инициализация таблиц"""
        async with self.pool.acquire() as conn:
            await conn.execute('''
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
            ''')
            
            await conn.execute('''
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
            ''')
        
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_rooms_creator ON rooms(creator_id)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_players_user ON players(user_id)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_players_room ON players(room_id)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_rooms_expires ON rooms(expires_at)')
            
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS image_cache (
                    url TEXT PRIMARY KEY,
                    file_id TEXT,
                    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    mode VARCHAR(20)
                )
            ''')
            
            logger.info("Database initialized")
    
    async def cleanup_old_rooms(self):
        """Очистка старых комнат (запускать периодически)"""
        async with self.pool.acquire() as conn:
            deleted = await conn.execute('''
                DELETE FROM rooms 
                WHERE expires_at < CURRENT_TIMESTAMP - INTERVAL '1 hour'
            ''')
            logger.info(f"Cleaned up old rooms")

    
    async def create_room(self, room_id: str, creator_id: int, mode: str = "clash") -> bool:
        """Создание новой комнаты"""
        async with self.pool.acquire() as conn:
            try:
                await conn.execute('''
                    INSERT INTO rooms (id, creator_id, mode, expires_at)
                    VALUES ($1, $2, $3, CURRENT_TIMESTAMP + INTERVAL '24 hours')
                ''', room_id, creator_id, mode)
                
                await self.add_player_to_room(creator_id, room_id)
                return True
            except asyncpg.UniqueViolationError:
                return False
    
    async def get_room(self, room_id: str) -> Optional[dict]:
        """Получение информации о комнате"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow('''
                SELECT * FROM rooms WHERE id = $1
            ''', room_id)
            return dict(row) if row else None
    
    async def update_room_game_state(self, room_id: str, word: str, spy_id: int, 
                                     card_url: str = None):
        """Обновление состояния игры в комнате"""
        async with self.pool.acquire() as conn:
            await conn.execute('''
                UPDATE rooms 
                SET word = $1, spy_id = $2, card_url = $3, 
                    game_started = TRUE, updated_at = CURRENT_TIMESTAMP
                WHERE id = $4
            ''', word, spy_id, card_url, room_id)
    
    async def reset_room_game(self, room_id: str):
        """Сброс игры в комнате"""
        async with self.pool.acquire() as conn:
            await conn.execute('''
                UPDATE rooms 
                SET word = NULL, spy_id = NULL, card_url = NULL,
                    game_started = FALSE, updated_at = CURRENT_TIMESTAMP
                WHERE id = $1
            ''', room_id)
            
            await conn.execute('''
                UPDATE players 
                SET role = NULL, word = NULL, card_url = NULL
                WHERE room_id = $1
            ''', room_id)
    
    async def delete_room(self, room_id: str):
        """Удаление комнаты"""
        async with self.pool.acquire() as conn:
            await conn.execute('DELETE FROM rooms WHERE id = $1', room_id)
    
    async def update_room_mode(self, room_id: str, mode: str):
        """Обновление режима комнаты"""
        async with self.pool.acquire() as conn:
            await conn.execute('''
                UPDATE rooms 
                SET mode = $1, updated_at = CURRENT_TIMESTAMP
                WHERE id = $2
            ''', mode, room_id)
    
    
    
    async def add_player_to_room(self, user_id: int, room_id: str) -> bool:
        """Добавление игрока в комнату"""
        async with self.pool.acquire() as conn:
            try:
                count = await conn.fetchval('''
                    SELECT COUNT(*) FROM players WHERE room_id = $1
                ''', room_id)
                
                if count >= 15:
                    return False
                
                await conn.execute('''
                    INSERT INTO players (user_id, room_id)
                    VALUES ($1, $2)
                    ON CONFLICT (user_id, room_id) DO NOTHING
                ''', user_id, room_id)
                return True
            except Exception as e:
                logger.error(f"Error adding player: {e}")
                return False
    
    async def remove_player_from_room(self, user_id: int, room_id: str):
        """Удаление игрока из комнаты"""
        async with self.pool.acquire() as conn:
            await conn.execute('''
                DELETE FROM players WHERE user_id = $1 AND room_id = $2
            ''', user_id, room_id)
    
    async def get_room_players(self, room_id: str) -> List[int]:
        """Получение списка игроков в комнате"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT user_id FROM players WHERE room_id = $1 ORDER BY joined_at
            ''', room_id)
            return [row['user_id'] for row in rows]
    
    async def get_player_data(self, user_id: int, room_id: str) -> Optional[dict]:
        """Получение данных игрока"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow('''
                SELECT * FROM players WHERE user_id = $1 AND room_id = $2
            ''', user_id, room_id)
            return dict(row) if row else None
    
    async def update_player_role(self, user_id: int, room_id: str, 
                                 role: str, word: str = None, card_url: str = None):
        """Обновление роли игрока"""
        async with self.pool.acquire() as conn:
            await conn.execute('''
                UPDATE players 
                SET role = $1, word = $2, card_url = $3
                WHERE user_id = $4 AND room_id = $5
            ''', role, word, card_url, user_id, room_id)
    
    async def get_user_room(self, user_id: int) -> Optional[str]:
        """Получение ID комнаты, в которой находится пользователь"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow('''
                SELECT room_id FROM players WHERE user_id = $1 LIMIT 1
            ''', user_id)
            return row['room_id'] if row else None
    
    async def get_room_creator(self, room_id: str) -> Optional[int]:
        """Получение создателя комнаты"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow('''
                SELECT creator_id FROM rooms WHERE id = $1
            ''', room_id)
            return row['creator_id'] if row else None
    
    async def transfer_room_ownership(self, room_id: str, new_creator_id: int):
        """Передача владения комнатой"""
        async with self.pool.acquire() as conn:
            await conn.execute('''
                UPDATE rooms 
                SET creator_id = $1, updated_at = CURRENT_TIMESTAMP
                WHERE id = $2
            ''', new_creator_id, room_id)
    
    async def get_all_rooms_stats(self) -> dict:
        """Статистика по всем комнатам (для мониторинга)"""
        async with self.pool.acquire() as conn:
            total_rooms = await conn.fetchval('SELECT COUNT(*) FROM rooms')
            active_rooms = await conn.fetchval('''
                SELECT COUNT(*) FROM rooms WHERE game_started = TRUE
            ''')
            total_players = await conn.fetchval('SELECT COUNT(*) FROM players')
            
            return {
                'total_rooms': total_rooms,
                'active_rooms': active_rooms,
                'total_players': total_players
            }


db = Database()