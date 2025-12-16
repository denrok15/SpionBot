import logging
import os
import asyncio
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from utils.background import periodic_cleanup
from handlers.commands import *
from dotenv import load_dotenv
from utils.decorators import create_decorators, room_locks
import nest_asyncio

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
nest_asyncio.apply()
logger = logging.getLogger(__name__)
load_dotenv()
decorators = create_decorators(db)
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
        logger.info("database connected successfully")
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