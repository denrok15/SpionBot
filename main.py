import logging
import random
import os
import asyncio
from typing import Dict, Optional, List
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from telegram.constants import ParseMode
from const import (
    dotaImages,
    namesDota,
    MODE_CLASH,
    MODE_DOTA,
    WORDS_CLASH,
    CARDS_CLASH,
)
from dotenv import load_dotenv
import asyncpg
from datetime import datetime
import aiohttp
from decorators import create_decorators, room_locks
import nest_asyncio

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
nest_asyncio.apply()
logger = logging.getLogger(__name__)
load_dotenv()

class Database:
    def __init__(self):
        self.pool = None
    
    async def connect(self, dsn: str, min_size: int = 5, max_size: int = 20):
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
    
    async def create_room(self, room_id: str, creator_id: int, mode: str = "clash") -> bool:
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
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow('SELECT * FROM rooms WHERE id = $1', room_id)
            return dict(row) if row else None
    
    async def update_room_game_state(self, room_id: str, word: str, spy_id: int, card_url: str = None):
        async with self.pool.acquire() as conn:
            await conn.execute('''
                UPDATE rooms 
                SET word = $1, spy_id = $2, card_url = $3, 
                    game_started = TRUE, updated_at = CURRENT_TIMESTAMP
                WHERE id = $4
            ''', word, spy_id, card_url, room_id)
    
    async def reset_room_game(self, room_id: str):
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
        async with self.pool.acquire() as conn:
            await conn.execute('DELETE FROM rooms WHERE id = $1', room_id)
    
    async def update_room_mode(self, room_id: str, mode: str):
        async with self.pool.acquire() as conn:
            await conn.execute('''
                UPDATE rooms 
                SET mode = $1, updated_at = CURRENT_TIMESTAMP
                WHERE id = $2
            ''', mode, room_id)
    
    async def add_player_to_room(self, user_id: int, room_id: str) -> bool:
        async with self.pool.acquire() as conn:
            count = await conn.fetchval('SELECT COUNT(*) FROM players WHERE room_id = $1', room_id)
            if count >= 15:
                return False
            try:
                await conn.execute('''
                    INSERT INTO players (user_id, room_id)
                    VALUES ($1, $2)
                    ON CONFLICT (user_id, room_id) DO NOTHING
                ''', user_id, room_id)
                return True
            except:
                return False
    
    async def remove_player_from_room(self, user_id: int, room_id: str):
        async with self.pool.acquire() as conn:
            await conn.execute('DELETE FROM players WHERE user_id = $1 AND room_id = $2', user_id, room_id)
    
    async def get_room_players(self, room_id: str) -> List[int]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch('SELECT user_id FROM players WHERE room_id = $1 ORDER BY joined_at', room_id)
            return [row['user_id'] for row in rows]
    
    async def get_player_data(self, user_id: int, room_id: str) -> Optional[dict]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow('SELECT * FROM players WHERE user_id = $1 AND room_id = $2', user_id, room_id)
            return dict(row) if row else None
    
    async def update_player_role(self, user_id: int, room_id: str, role: str, word: str = None, card_url: str = None):
        async with self.pool.acquire() as conn:
            await conn.execute('''
                UPDATE players 
                SET role = $1, word = $2, card_url = $3
                WHERE user_id = $4 AND room_id = $5
            ''', role, word, card_url, user_id, room_id)
    
    async def get_user_room(self, user_id: int) -> Optional[str]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow('SELECT room_id FROM players WHERE user_id = $1 LIMIT 1', user_id)
            return row['room_id'] if row else None
    
    async def get_room_creator(self, room_id: str) -> Optional[int]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow('SELECT creator_id FROM rooms WHERE id = $1', room_id)
            return row['creator_id'] if row else None
    
    async def transfer_room_ownership(self, room_id: str, new_creator_id: int):
        async with self.pool.acquire() as conn:
            await conn.execute('UPDATE rooms SET creator_id = $1 WHERE id = $2', new_creator_id, room_id)
    
    async def cleanup_old_rooms(self):
        async with self.pool.acquire() as conn:
            await conn.execute("DELETE FROM rooms WHERE expires_at < NOW() - INTERVAL '1 hour'")
    
    async def get_all_rooms_stats(self) -> dict:
        async with self.pool.acquire() as conn:
            total_rooms = await conn.fetchval('SELECT COUNT(*) FROM rooms')
            active_rooms = await conn.fetchval("SELECT COUNT(*) FROM rooms WHERE game_started = TRUE")
            total_players = await conn.fetchval('SELECT COUNT(*) FROM players')
            return {'total_rooms': total_rooms, 'active_rooms': active_rooms, 'total_players': total_players}
    
    async def get_cached_image(self, url: str) -> Optional[str]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow('''
                SELECT file_id FROM image_cache 
                WHERE url = $1 AND cached_at > CURRENT_TIMESTAMP - INTERVAL '7 days'
            ''', url)
            return row['file_id'] if row else None
    
    async def cache_image(self, url: str, file_id: str, mode: str):
        async with self.pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO image_cache (url, file_id, mode, cached_at)
                VALUES ($1, $2, $3, CURRENT_TIMESTAMP)
                ON CONFLICT (url) DO UPDATE 
                SET file_id = EXCLUDED.file_id, cached_at = EXCLUDED.cached_at
            ''', url, file_id, mode)
    
    async def cleanup_image_cache(self):
        async with self.pool.acquire() as conn:
            await conn.execute("DELETE FROM image_cache WHERE cached_at < CURRENT_TIMESTAMP - INTERVAL '30 days'")


db = Database()
decorators = create_decorators(db)

DEFAULT_MODE = MODE_CLASH


def get_words_and_cards_by_mode(mode: str):
    if mode == MODE_DOTA:
        return namesDota, dotaImages
    return WORDS_CLASH, CARDS_CLASH

def get_theme_name(mode: str) -> str:
    if mode == MODE_DOTA:
        return "Герои Dota 2"
    return "Карты Clash Royale"

def get_main_keyboard():
    return ReplyKeyboardMarkup(
        [
            ["🎮 Создать комнату", "🔗 Присоединиться"],
            ["▶️ Начать игру", "🔄 Перезапустить"],
            ["📖 Правила","🚪 Выйти из комнаты"],
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )

def get_room_keyboard():
    return ReplyKeyboardMarkup(
        [
            ["▶️ Начать игру", "🔄 Перезапустить"],
            ["🚪 Выйти из комнаты","🏠 Главное меню"],
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )


@decorators.rate_limit()
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = get_main_keyboard()
    room_id = await db.get_user_room(update.effective_user.id)
    
    if room_id:
        room = await db.get_room(room_id)
        mode = room.get("mode", DEFAULT_MODE) if room else DEFAULT_MODE
    else:
        mode = DEFAULT_MODE
    
    theme_name = get_theme_name(mode)
    await update.message.reply_text(
        "🎮 Добро пожаловать в игру 'Шпион'!\n\n"
        "📌 Используйте кнопки ниже или команды:\n"
        "/create - создать комнату\n"
        "/join <ID комнаты> - присоединиться к комнате\n"
        "/startgame - начать игру\n"
        "/restart - перезапустить игру\n"
        "/word - узнать своё слово (в личке с ботом)\n"
        "/cards - посмотреть все карты\n"
        "/rules - правила игры\n\n"
        f"🎴 Текущая тематика: {theme_name}\n"
        "Доступные режимы: ClashRoyale и Dota2\n"
        "Создатель комнаты может сменить режим командами /mode_clash и /mode_dota\n\n"
        "👥 Игру создали It tut Денис и Артур!",
        reply_markup=keyboard
    )

@decorators.rate_limit()
@decorators.private_chat_only()
async def create_room(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    for _ in range(10):
        room_id = str(random.randint(1000, 9999))
        room = await db.get_room(room_id)
        if not room:
            break
    else:
        await update.message.reply_text("❌ Не удалось создать комнату. Попробуйте ещё раз.")
        return

    success = await db.create_room(room_id, user_id, DEFAULT_MODE)
    if not success:
        await update.message.reply_text("❌ Ошибка при создании комнаты.")
        return

    words, _ = get_words_and_cards_by_mode(DEFAULT_MODE)
    keyboard = get_room_keyboard()
    
    await update.message.reply_text(
        f"✅ Комната создана!\n\n"
        f"ID комнаты: <code>{room_id}</code>\n"
        f"Отправьте этот ID другим игрокам\n\n"
        f"👥 Игроков: 1/15\n"
        f"🎴 Режим: {get_theme_name(DEFAULT_MODE)}\n"
        f"Доступно слов: {len(words)}\n"
        f"Создатель комнаты может сменить режим командами /mode_clash и /mode_dota\n\n"
        f"Для начала игры нажмите '▶️ Начать игру'",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )

@decorators.rate_limit()
@decorators.private_chat_only()
async def join_room(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if update.message.text == "🔗 Присоединиться":
        await update.message.reply_text("📝 Введите ID комнаты для присоединения:")
        return

    if len(context.args) == 0 and update.message.text != "🔗 Присоединиться":
        if update.message.text and update.message.text.isdigit():
            room_id = update.message.text
        else:
            await update.message.reply_text("❌ Использование: /join <ID_комнаты> или отправьте ID комнаты")
            return
    else:
        room_id = context.args[0]

    lock = room_locks.get_lock(room_id)
    async with lock:
        room = await db.get_room(room_id)
        if not room:
            await update.message.reply_text("❌ Комната не найдена!")
            return

        if room["game_started"]:
            await update.message.reply_text("❌ Игра уже началась!")
            return

        current_room = await db.get_user_room(user_id)
        if current_room == room_id:
            await update.message.reply_text("❌ Вы уже в этой комнате!")
            return

        success = await db.add_player_to_room(user_id, room_id)
        if not success:
            await update.message.reply_text("❌ Комната переполнена!")
            return

    players = await db.get_room_players(room_id)
    keyboard = get_room_keyboard()
    
    await update.message.reply_text(
        f"✅ Вы присоединились к комнате {room_id}!\n\n"
        f"👥 Игроков: {len(players)}/15\n"
        f"Ожидайте начала игры...",
        reply_markup=keyboard
    )

    creator_id = room["creator_id"]
    try:
        await context.bot.send_message(
            creator_id,
            f"📢 Игрок присоединился! Теперь игроков: {len(players)}"
        )
    except:
        pass

@decorators.rate_limit()
@decorators.creator_only()
@decorators.room_lock()
async def start_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    logger.info(f"🔄 USER {user_id} пытается начать игру")
    room_id = await db.get_user_room(user_id)
    
    if not room_id:
        logger.info(f"❌ USER {user_id} не в комнате")
        await update.message.reply_text("❌ Вы не в комнате!")
        return

    logger.info(f"🔒 USER {user_id} получил блокировку комнаты {room_id}")
    room = await db.get_room(room_id)
    if not room:
        logger.info(f"❌ Комната {room_id} не найдена в БД")
        await update.message.reply_text("❌ Комната не найдена!")
        return

    players = await db.get_room_players(room_id)
    logger.info(f"👥 Игроки в комнате {room_id}: {players}")
    if len(players) < 2:
        await update.message.reply_text("❌ Нужно минимум 2 игрока!")
        return

    mode = room.get("mode", DEFAULT_MODE)
    words, cards_map = get_words_and_cards_by_mode(mode)

    word = random.choice(words)
    card_url = cards_map.get(word, "")
    spy = random.choice(players)

    await db.update_room_game_state(room_id, word, spy, card_url)

    
    for player_id in players:
        if player_id == spy:
            await db.update_player_role(player_id, room_id, "шпион")
            
    
            cached_file_id = await db.get_cached_image(
                "https://i.pinimg.com/originals/41/15/70/4115707ee950d4b0aba69664f7986ae5.png"
            )
            
            try:
                if cached_file_id:
                    await context.bot.send_photo(
                        chat_id=player_id,
                        photo=cached_file_id,
                        caption=f"🎭 Вы - ШПИОН!\n\n❌ Вы не знаете слово!\n🎯 Ваша задача - понять слово.\n👥 Игроков: {len(players)}\n\n💡 Подсказка: это объект из {get_theme_name(mode)}"
                    )
                else:
                    result = await context.bot.send_photo(
                        chat_id=player_id,
                        photo="https://i.pinimg.com/originals/41/15/70/4115707ee950d4b0aba69664f7986ae5.png",
                        caption=f"🎭 Вы - ШПИОН!\n\n❌ Вы не знаете слово!\n🎯 Ваша задача - понять слово.\n👥 Игроков: {len(players)}\n\n💡 Подсказка: это объект из {get_theme_name(mode)}"
                    )
                    if hasattr(result, 'photo') and result.photo:
                        await db.cache_image(
                            "https://i.pinimg.com/originals/41/15/70/4115707ee950d4b0aba69664f7986ae5.png",
                            result.photo[-1].file_id,
                            mode
                        )
            except Exception as e:
                logger.error(f"Error sending spy photo: {e}")
                await context.bot.send_message(
                    player_id,
                    f"🎭 Вы - ШПИОН!\n\n❌ Вы не знаете слово!\n🎯 Ваша задача - понять слово.\n👥 Игроков: {len(players)}"
                )
        else:
            await db.update_player_role(player_id, room_id, "мирный", word, card_url)
            
            if card_url:
                cached_file_id = await db.get_cached_image(card_url)
                
                try:
                    if cached_file_id:
                        await context.bot.send_photo(
                            chat_id=player_id,
                            photo=cached_file_id,
                            caption=f"✅ Вы - мирный игрок!\n\n🎴 Загаданная карта: <b>{word}</b>\n👥 Игроков: {len(players)}\n⚠️ Среди вас есть шпион!",
                            parse_mode=ParseMode.HTML
                        )
                    else:
                        result = await context.bot.send_photo(
                            chat_id=player_id,
                            photo=card_url,
                            caption=f"✅ Вы - мирный игрок!\n\n🎴 Загаданная карта: <b>{word}</b>\n👥 Игроков: {len(players)}\n⚠️ Среди вас есть шпион!",
                            parse_mode=ParseMode.HTML
                        )
                        if hasattr(result, 'photo') and result.photo:
                            await db.cache_image(card_url, result.photo[-1].file_id, mode)
                except Exception as e:
                    logger.error(f"Error sending card photo: {e}")
                    await context.bot.send_message(
                        player_id,
                        f"✅ Вы - мирный игрок!\n\n🎴 Загаданная карта: <b>{word}</b>\n👥 Игроков: {len(players)}\n⚠️ Среди вас есть шпион!",
                        parse_mode=ParseMode.HTML
                    )
            else:
                await context.bot.send_message(
                    player_id,
                    f"✅ Вы - мирный игрок!\n\n🎴 Загаданная карта: <b>{word}</b>\n👥 Игроков: {len(players)}\n⚠️ Среди вас есть шпион!",
                    parse_mode=ParseMode.HTML
                )

    for player_id in players:
        try:
            await context.bot.send_message(
                player_id,
                f"🎮 Игра началась!\n👥 Игроков: {len(players)}\n🎴 Тема: {get_theme_name(mode)}\n\n💬 Можно начинать обсуждение!"
            )
        except:
            pass

@decorators.rate_limit()
@decorators.creator_only()
@decorators.room_lock()
async def restart_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    room_id = await db.get_user_room(user_id)
    
    if not room_id:
        await update.message.reply_text("❌ Вы не в комнате!")
        return

    room = await db.get_room(room_id)
    if not room:
        await update.message.reply_text("❌ Комната не найдена!")
        return

    await db.reset_room_game(room_id)
    players = await db.get_room_players(room_id)
    words, _ = get_words_and_cards_by_mode(room["mode"])

    keyboard = get_room_keyboard()
    await update.message.reply_text(
        f"🔄 Игра перезапущена!\n\n"
        f"ID комнаты: <code>{room_id}</code>\n"
        f"👥 Игроков: {len(players)}\n"
        f"🎴 Режим: {get_theme_name(room['mode'])}\n"
        f"Доступно слов: {len(words)}\n\n"
        f"Для начала новой игры нажмите '▶️ Начать игру'",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )

    for player_id in players:
        if player_id != user_id:
            try:
                await context.bot.send_message(
                    player_id,
                    f"🔄 Создатель перезапустил игру!\nОжидайте начала новой игры."
                )
            except:
                pass

@decorators.rate_limit()
@decorators.private_chat_only()
@decorators.rate_limit()
@decorators.private_chat_only()
async def get_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    room_id = await db.get_user_room(user_id)

    room_id = await db.get_user_room(user_id)
    if not room_id:
        await update.message.reply_text("❌ Вы не в игре!")
        return

    room = await db.get_room(room_id)
    if not room or not room["game_started"]:
        await update.message.reply_text("❌ Игра ещё не началась!")
        return

    player_data = await db.get_player_data(user_id, room_id)
    if not player_data:
        await update.message.reply_text("❌ Данные игрока не найдены!")
        return

    if player_data["role"] == "шпион":
        try:
            cached_file_id = await db.get_cached_image(
                "https://i.pinimg.com/originals/41/15/70/4115707ee950d4b0aba69664f7986ae5.png"
            )
            
            if cached_file_id:
                await context.bot.send_photo(
                    chat_id=user_id,
                    photo=cached_file_id,
                    caption=f"🎭 Вы - ШПИОН!\n\n❌ Вы не знаете слово!\n👥 Игроков: {len(await db.get_room_players(room_id))}"
                )
            else:
                await context.bot.send_photo(
                    chat_id=user_id,
                    photo="https://i.pinimg.com/originals/41/15/70/4115707ee950d4b0aba69664f7986ae5.png",
                    caption=f"🎭 Вы - ШПИОН!\n\n❌ Вы не знаете слово!\n👥 Игроков: {len(await db.get_room_players(room_id))}"
                )
        except:
            await update.message.reply_text(
                f"🎭 Вы - ШПИОН!\n\n❌ Вы не знаете слово!\n👥 Игроков: {len(await db.get_room_players(room_id))}"
            )
    else:
        if player_data["card_url"]:
            cached_file_id = await db.get_cached_image(player_data["card_url"])
            
            try:
                if cached_file_id:
                    await context.bot.send_photo(
                        chat_id=user_id,
                        photo=cached_file_id,
                        caption=f"✅ Вы - мирный игрок!\n\n🎴 Загаданная карта: <b>{player_data['word']}</b>\n👥 Игроков: {len(await db.get_room_players(room_id))}",
                        parse_mode=ParseMode.HTML
                    )
                else:
                    await context.bot.send_photo(
                        chat_id=user_id,
                        photo=player_data["card_url"],
                        caption=f"✅ Вы - мирный игрок!\n\n🎴 Загаданная карта: <b>{player_data['word']}</b>\n👥 Игроков: {len(await db.get_room_players(room_id))}",
                        parse_mode=ParseMode.HTML
                    )
            except:
                await update.message.reply_text(
                    f"✅ Вы - мирный игрок!\n\n🎴 Загаданная карта: <b>{player_data['word']}</b>\n👥 Игроков: {len(await db.get_room_players(room_id))}",
                    parse_mode=ParseMode.HTML
                )
        else:
            await update.message.reply_text(
                f"✅ Вы - мирный игрок!\n\n🎴 Загаданная карта: <b>{player_data['word']}</b>\n👥 Игроков: {len(await db.get_room_players(room_id))}",
                parse_mode=ParseMode.HTML
            )

@decorators.rate_limit()
async def show_players(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    room_id = await db.get_user_room(user_id)
    
    if not room_id:
        await update.message.reply_text("❌ Вы не в комнате!")
        return

    room = await db.get_room(room_id)
    players = await db.get_room_players(room_id)
    
    players_list = ""
    for i, player_id in enumerate(players):
        player_data = await db.get_player_data(player_id, room_id)
        role = player_data["role"] if player_data and player_data["role"] else "ожидает"
        players_list += f"• Игрок {i+1} ({role})\n"
    
    status = "🎮 Игра начата" if room["game_started"] else "⏳ Ожидание"
    current_word = f"\n🎴 Текущее слово: {room['word']}" if room["word"] else ""
    
    await update.message.reply_text(
        f"👥 Комната {room_id}:\n\n"
        f"Игроков: {len(players)}\n"
        f"Режим: {get_theme_name(room['mode'])}\n"
        f"Статус: {status}{current_word}\n\n"
        f"{players_list}"
    )

@decorators.rate_limit()
@decorators.room_lock()
async def leave_room(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    room_id = await db.get_user_room(user_id)
    
    if not room_id:
        await update.message.reply_text("❌ Вы не в комнате!")
        return

    await db.remove_player_from_room(user_id, room_id)
    
    players = await db.get_room_players(room_id)
    
    if not players:
        await db.delete_room(room_id)
    else: 
        creator_id = await db.get_room_creator(room_id)
        if creator_id == user_id and players:
            await db.transfer_room_ownership(room_id, players[0])
            try:
                await context.bot.send_message(
                    players[0],
                    f"👑 Вы стали новым создателем комнаты {room_id}!"
                )
            except:
                pass

    keyboard = get_main_keyboard()
    await update.message.reply_text("✅ Вы вышли из комнаты!", reply_markup=keyboard)

@decorators.rate_limit()
async def rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = get_main_keyboard()
    room_id = await db.get_user_room(update.effective_user.id)
    
    if room_id:
        room = await db.get_room(room_id)
        mode = room.get("mode", DEFAULT_MODE) if room else DEFAULT_MODE
    else:
        mode = DEFAULT_MODE
    
    theme_name = get_theme_name(mode)
    
    await update.message.reply_text(
        "📖 Правила игры 'Шпион':\n\n"
        "1) Все игроки кроме шпиона видят одинаковое слово\n"
        "2) Шпион не знает слово\n"
        "3) Игроки по очереди задают вопросы о слове\n"
        "4) Цель шпиона - определить слово\n"
        "5) Цель остальных - вычислить шпиона\n\n"
        f"🖼️ Каждому слову соответствует объект из выбранной игры ({theme_name})!\n"
        "Игра проходит устно, бот только раздаёт роли!",
        reply_markup=keyboard
    )

@decorators.rate_limit()
async def show_cards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    room_id = await db.get_user_room(user_id)
    
    if room_id:
        room = await db.get_room(room_id)
        mode = room.get("mode", DEFAULT_MODE) if room else DEFAULT_MODE
        keyboard = get_room_keyboard()
    else:
        mode = DEFAULT_MODE
        keyboard = get_main_keyboard()
    
    words, cards_map = get_words_and_cards_by_mode(mode)
    theme_name = get_theme_name(mode)

    cards_with_images = []
    cards_without_images = []

    for word in words:
        if cards_map.get(word):
            cards_with_images.append(f"✅ {word}")
        else:
            cards_without_images.append(f"❌ {word}")

    response = f"🎴 Все объекты ({theme_name}) в игре:\n\n"

    if cards_with_images:
        response += "📸 Карты с изображениями:\n" + "\n".join(cards_with_images[:10]) + "\n\n"

    if cards_without_images:
        response += "🖼️ Карты без изображений:\n" + "\n".join(cards_without_images[:10]) + "\n\n"

    if len(cards_with_images) + len(cards_without_images) > 20:
        response += f"... и ещё {len(words) - 20} вариантов\n\n"

    response += f"Всего вариантов: {len(words)}\n"
    response += f"С изображениями: {len(cards_with_images)}\n"
    response += f"Без изображений: {len(cards_without_images)}"

    await update.message.reply_text(response, reply_markup=keyboard)

@decorators.rate_limit()
@decorators.private_chat_only()
@decorators.creator_only()
@decorators.room_lock()
async def set_mode_clash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    room_id = await db.get_user_room(user_id)
    
    if not room_id:
        await update.message.reply_text("❌ Сначала создайте комнату /create, чтобы выбрать режим!")
        return

    room = await db.get_room(room_id)
    if not room:
        await update.message.reply_text("❌ Комната не найдена!")
        return

    if room["game_started"]:
        await update.message.reply_text("❌ Нельзя менять режим во время игры!")
        return

    await db.update_room_mode(room_id, MODE_CLASH)
    words, _ = get_words_and_cards_by_mode(MODE_CLASH)

    await update.message.reply_text(
        f"✅ Режим изменён на {get_theme_name(MODE_CLASH)}.\n"
        f"Доступно слов: {len(words)}"
    )

@decorators.rate_limit()
@decorators.private_chat_only()
@decorators.creator_only()
@decorators.room_lock()
async def set_mode_dota(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    room_id = await db.get_user_room(user_id)
    
    if not room_id:
        await update.message.reply_text("❌ Сначала создайте комнату /create, чтобы выбрать режим!")
        return

    room = await db.get_room(room_id)
    if not room:
        await update.message.reply_text("❌ Комната не найдена!")
        return

    if room["game_started"]:
        await update.message.reply_text("❌ Нельзя менять режим во время игры!")
        return

    await db.update_room_mode(room_id, MODE_DOTA)
    words, _ = get_words_and_cards_by_mode(MODE_DOTA)

    await update.message.reply_text(
        f"✅ Режим изменён на {get_theme_name(MODE_DOTA)}.\n"
        f"Доступно героев: {len(words)}"
    )

@decorators.rate_limit()
async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    room_id = await db.get_user_room(user_id)
    
    if room_id:
        players = await db.get_room_players(room_id)
        room = await db.get_room(room_id)
        
        await update.message.reply_text(
            f"📊 Статистика комнаты {room_id}:\n\n"
            f"👥 Игроков: {len(players)}\n"
            f"🎯 Режим: {get_theme_name(room['mode'])}\n"
            f"🎮 Игра начата: {'Да' if room['game_started'] else 'Нет'}\n"
            f"📅 Создана: {room['created_at'].strftime('%Y-%m-%d %H:%M')}"
        )
    else:
        stats = await db.get_all_rooms_stats()
        await update.message.reply_text(
            f"📊 Общая статистика бота:\n\n"
            f"🏠 Всего комнат: {stats['total_rooms']}\n"
            f"🎮 Активных игр: {stats['active_rooms']}\n"
            f"👤 Всего игроков: {stats['total_players']}"
        )

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id

    if text == "🎮 Создать комнату":
        await create_room(update, context)
    elif text == "🔗 Присоединиться":
        await join_room(update, context)
    elif text == "▶️ Начать игру":
        await start_game(update, context)
    elif text == "🔄 Перезапустить":
        await restart_game(update, context)
    elif text == "📖 Правила":
        await rules(update, context)
    elif text == "🎴 Все карты":
        await show_cards(update, context)
    elif text == "👤 Моя роль/слово":
        await get_word(update, context)
    elif text == "👥 Игроки в комнате":
        await show_players(update, context)
    elif text == "🚪 Выйти из комнаты":
        await leave_room(update, context)
    elif text == "ℹ️ Помощь" or text == "🏠 Главное меню":
        await start(update, context)
    elif text.isdigit() and len(text) == 4:
        context.args = [text]
        await join_room(update, context)
    else:
        await update.message.reply_text("Используйте кнопки меню или команды.")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(msg="Exception while handling an update:", exc_info=context.error)
    if update and update.effective_chat:
        try:
            await update.effective_chat.send_message(
                "❌ Произошла ошибка. Попробуйте еще раз."
            )
        except:
            pass

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

async def main():
    API_TOKEN = os.getenv('API_TOKEN')
    DATABASE_URL = os.getenv('DATABASE_URL')
    
    if not API_TOKEN or API_TOKEN == "ВАШ_API_КЛЮЧ":
        print("❌ Установите API_TOKEN в .env файле!")
        return
    
    if not DATABASE_URL:
        print("❌ Установите DATABASE_URL в .env файле!")
        return

    try:
        await db.connect(DATABASE_URL, min_size=5, max_size=20)
        logger.info("Database connected successfully")
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        return

    asyncio.create_task(periodic_cleanup())

    application = Application.builder().token(API_TOKEN).build()

    
    handlers = [
        CommandHandler("start", start),
        CommandHandler("create", create_room),
        CommandHandler("join", join_room),
        CommandHandler("startgame", start_game),
        CommandHandler("restart", restart_game),
        CommandHandler("word", get_word),
        CommandHandler("players", show_players),
        CommandHandler("leave", leave_room),
        CommandHandler("rules", rules),
        CommandHandler("cards", show_cards),
        CommandHandler("mode_clash", set_mode_clash),
        CommandHandler("mode_dota", set_mode_dota),
        CommandHandler("help", start),
        CommandHandler("menu", start),
        CommandHandler("stats", show_stats),
    ]
    
    for handler in handlers:
        application.add_handler(handler)

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    application.add_error_handler(error_handler)

    logger.info("🚀 Bot starting...")
    
    try:
        await application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
            close_loop=False
        )
    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        if db.pool:
            await db.pool.close()

if __name__ == '__main__':
    asyncio.run(main())
