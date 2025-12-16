

import asyncio
import time
import logging
from typing import Dict, Optional
from collections import defaultdict, deque
from functools import wraps

from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


class RoomLocks:
    """Менеджер блокировок для комнат"""
    
    def __init__(self):
        self._locks: Dict[str, asyncio.Lock] = {}
        logger.debug("RoomLocks инициализирован")
    
    def get_lock(self, room_id: str) -> asyncio.Lock:
        """Получение блокировки для комнаты"""
        if room_id not in self._locks:
            self._locks[room_id] = asyncio.Lock()
            logger.debug(f"Создана блокировка для комнаты {room_id}")
        return self._locks[room_id]
    
    def cleanup(self, max_age_hours: int = 24):
        """Очистка старых блокировок (можно вызывать периодически)"""

        pass



class RateLimiter:
    """Класс для ограничения частоты запросов"""
    
    def __init__(self, max_requests: int = 10, period: float = 1.0):
        """
        Args:
            max_requests: Максимальное количество запросов
            period: Период времени в секундах
        """
        self.max_requests = max_requests
        self.period = period
        self._requests: Dict[int, deque] = defaultdict(deque)
        logger.debug(f"RateLimiter инициализирован: {max_requests}/{period}сек")
    
    async def is_allowed(self, user_id: int) -> bool:
        """Проверяет, разрешен ли запрос пользователю"""
        current_time = time.time()
        
        if user_id in self._requests:
            while (self._requests[user_id] and 
                   current_time - self._requests[user_id][0] > self.period):
                self._requests[user_id].popleft()
        
        if (user_id in self._requests and 
            len(self._requests[user_id]) >= self.max_requests):
            logger.debug(f"Лимит превышен для пользователя {user_id}")
            return False
        
        if user_id not in self._requests:
            self._requests[user_id] = deque()
        self._requests[user_id].append(current_time)
        
        return True
    
    def cleanup_old_users(self, max_inactive_hours: int = 24):
        """Очистка данных неактивных пользователей"""
        current_time = time.time()
        inactive_threshold = current_time - (max_inactive_hours * 3600)
        
        users_to_remove = []
        for user_id, requests in self._requests.items():
            if not requests or requests[-1] < inactive_threshold:
                users_to_remove.append(user_id)
        
        for user_id in users_to_remove:
            del self._requests[user_id]
        
        if users_to_remove:
            logger.debug(f"Очищено {len(users_to_remove)} неактивных пользователей")


class BotDecorators:
    """
    Класс декораторов для Telegram бота.
    Использование:
        decorators = BotDecorators(db_instance, room_locks_instance)
    """
    
    def __init__(self, db_instance, room_locks_instance: Optional[RoomLocks] = None):
        """
        Args:
            db_instance: Экземпляр класса Database
            room_locks_instance: Экземпляр RoomLocks (опционально)
        """
        self.db = db_instance
        self.room_locks = room_locks_instance or RoomLocks()
        self.rate_limiter = RateLimiter(max_requests=10, period=1.0)
        logger.info("BotDecorators инициализирован")
    
    # ===== ОСНОВНЫЕ ДЕКОРАТОРЫ =====
    
    def room_lock(self):
        """
        Декоратор для блокировки комнаты.
        Гарантирует, что только один пользователь может изменять комнату одновременно.
        
        Использование:
            @decorators.room_lock()
            async def start_game(update, context):
                ...
        """
        def decorator(func):
            @wraps(func)
            async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
                user_id = update.effective_user.id
                
                # Получаем комнату пользователя
                room_id = await self.db.get_user_room(user_id)
                
                if not room_id:
                    # Пользователь не в комнате - просто выполняем функцию
                    return await func(update, context, *args, **kwargs)
                
                # Получаем блокировку для комнаты
                lock = self.room_locks.get_lock(room_id)
                
                # Выполняем под блокировкой
                logger.debug(f"🔒 User {user_id} блокирует комнату {room_id} для {func.__name__}")
                async with lock:
                    try:
                        result = await func(update, context, *args, **kwargs)
                        logger.debug(f"✅ User {user_id} завершил {func.__name__} в комнате {room_id}")
                        return result
                    except Exception as e:
                        logger.error(f"❌ Ошибка в {func.__name__} у user {user_id}: {e}")
                        raise
                
            return wrapper
        return decorator
    
    def rate_limit(self, max_requests: int = 10, period: float = 1.0):
        """
        Декоратор для ограничения запросов.
        Предотвращает спам и DoS-атаки.
        
        Args:
            max_requests: Максимальное количество запросов
            period: Период времени в секундах
            
        Использование:
            @decorators.rate_limit(max_requests=5, period=1.0)
            async def command(update, context):
                ...
        """
        limiter = RateLimiter(max_requests=max_requests, period=period)
        
        def decorator(func):
            @wraps(func)
            async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
                user_id = update.effective_user.id
                
                if not await limiter.is_allowed(user_id):
                    logger.warning(f"🚫 Rate limit exceeded for user {user_id} in {func.__name__}")
                    
                    last_warning_key = f"rate_limit_warning_{user_id}"
                    last_warning_time = context.user_data.get(last_warning_key, 0)
                    
                    if time.time() - last_warning_time > 5:
                        try:
                            await update.message.reply_text(
                                "⏳ Пожалуйста, не так быстро! Подождите секунду..."
                            )
                            context.user_data[last_warning_key] = time.time()
                        except Exception as e:
                            logger.error(f"Ошибка отправки rate limit предупреждения: {e}")
                    
                    return
                
                return await func(update, context, *args, **kwargs)
            
            return wrapper
        return decorator
    
    def creator_only(self):
        """
        Декоратор только для создателя комнаты.
        """
        def decorator(func):
            @wraps(func)
            async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
                user_id = update.effective_user.id
                
                room_id = await self.db.get_user_room(user_id)
                
                if not room_id:
                    await update.message.reply_text("❌ Вы не в комнате!")
                    return
                
                room = await self.db.get_room(room_id)
                if not room:
                    await update.message.reply_text("❌ Комната не найдена!")
                    return
                
                if room["creator_id"] != user_id:
                    await update.message.reply_text("⛔ Эта команда только для создателя комнаты!")
                    return
                
                return await func(update, context, *args, **kwargs)
            
            return wrapper
        return decorator
    
    def private_chat_only(self):
        """
        Декоратор только для личных сообщений с ботом.
        """
        def decorator(func):
            @wraps(func)
            async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
                chat_type = update.effective_chat.type
                
                if chat_type != "private":
                    await update.message.reply_text(
                        "❌ Эта команда работает только в личном чате с ботом!\n"
                        "Напишите мне в личные сообщения."
                    )
                    return
                
                return await func(update, context, *args, **kwargs)
            
            return wrapper
        return decorator
    
    def game_not_started(self):
        """
        Декоратор только если игра еще не начата.
        """
        def decorator(func):
            @wraps(func)
            async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
                user_id = update.effective_user.id
                
                room_id = await self.db.get_user_room(user_id)
                
                if not room_id:
                    await update.message.reply_text("❌ Вы не в комнате!")
                    return
                
                room = await self.db.get_room(room_id)
                if not room:
                    await update.message.reply_text("❌ Комната не найдена!")
                    return
                
                if room.get("game_started", False):
                    await update.message.reply_text(
                        "❌ Игра уже начата!\n"
                        "Дождитесь окончания или перезапустите игру."
                    )
                    return
                
                return await func(update, context, *args, **kwargs)
            
            return wrapper
        return decorator
    
    def protected_command(self, max_requests: int = 5):
        """
        Комбинированный декоратор для защищенных команд.
        Включает: rate_limit + private_chat_only + creator_only (если применимо)
        """
        def decorator(func):
            @wraps(func)
            @self.rate_limit(max_requests=max_requests)
            @self.private_chat_only()
            async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
                return await func(update, context, *args, **kwargs)
            
            return wrapper
        return decorator
    
    def game_command(self):
        """
        Комбинированный декоратор для игровых команд.
        Включает: rate_limit + room_lock + creator_only
        """
        def decorator(func):
            @wraps(func)
            @self.rate_limit(max_requests=5)
            @self.room_lock()
            @self.creator_only()
            async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
                return await func(update, context, *args, **kwargs)
            
            return wrapper
        return decorator


room_locks = RoomLocks()
rate_limiter = RateLimiter()


def create_decorators(db_instance):
    """Создает экземпляр BotDecorators с переданной БД"""
    return BotDecorators(db_instance, room_locks)