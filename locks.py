import asyncio
from typing import Dict
import logging

logger = logging.getLogger(__name__)

class RoomLocks:
    """Менеджер блокировок для комнат"""
    
    def __init__(self):
        self._locks: Dict[str, asyncio.Lock] = {}
        self._cleanup_task = None
    
    def get_lock(self, room_id: str) -> asyncio.Lock:
        """Получение блокировки для комнаты"""
        if room_id not in self._locks:
            self._locks[room_id] = asyncio.Lock()
        return self._locks[room_id]
    
    async def cleanup_old_locks(self):
        """Очистка старых блокировок"""
        pass

class RateLimiter:
    """Ограничитель запросов"""
    
    def __init__(self, max_requests: int = 5, period: float = 1.0):
        self.max_requests = max_requests
        self.period = period
        self.user_requests: Dict[int, list] = {}
    
    async def is_allowed(self, user_id: int) -> bool:
        """Проверка, можно ли выполнить запрос"""
        import time
        now = time.time()
        
        if user_id not in self.user_requests:
            self.user_requests[user_id] = []
        
        self.user_requests[user_id] = [
            req_time for req_time in self.user_requests[user_id]
            if now - req_time < self.period
        ]
        
        if len(self.user_requests[user_id]) >= self.max_requests:
            return False
        
        self.user_requests[user_id].append(now)
        return True