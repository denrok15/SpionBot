import asyncio
import logging
import os

import nest_asyncio
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    PreCheckoutQueryHandler,
    filters,
)

from database.actions import db
from handlers.commands import (
    check_subscription_callback,
    create_room,
    donate,
    error_handler,
    get_word,
    handle_text_message,
    join_room,
    leave_room,
    precheckout_callback,
    restart_game,
    rules,
    set_mode_clash,
    set_mode_dota,
    show_cards,
    show_players,
    show_stats,
    start,
    single_mode,
    single_mode_callback,
    start_game,
    successful_payment_callback,
    personal_account,
    buy_hint,
    buy_hint_type_callback,
    buy_hint_confirm_callback,
    buy_hint_cancel_callback,
    cabinet_action_callback,
    donate_amount_callback,
)
from utils.background import generate_clue, periodic_cleanup

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
nest_asyncio.apply()
logger = logging.getLogger(__name__)
load_dotenv()


async def main():
    API_TOKEN = os.getenv("API_TOKEN")
    DATABASE_URL = os.getenv("DATABASE_URL")

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
    #asyncio.create_task(generate_clue())

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
        CommandHandler("menu", start),
        CommandHandler("single", single_mode),
        CommandHandler("stats", show_stats),
        CommandHandler("account", personal_account),
        CommandHandler("buy_hint", buy_hint),
    ]
    application.add_handler(
        CallbackQueryHandler(check_subscription_callback, pattern="check_subscription")
    )
    application.add_handler(
        CallbackQueryHandler(single_mode_callback, pattern=r"^single:")
    )
    application.add_handler(
        CallbackQueryHandler(buy_hint_type_callback, pattern=r"^buy_type:")
    )
    application.add_handler(
        CallbackQueryHandler(buy_hint_confirm_callback, pattern=r"^buy_confirm:")
    )
    application.add_handler(
        CallbackQueryHandler(buy_hint_cancel_callback, pattern="buy_cancel")
    )
    application.add_handler(
        CallbackQueryHandler(cabinet_action_callback, pattern=r"^cabinet:")
    )
    application.add_handler(
        CallbackQueryHandler(donate_amount_callback, pattern=r"^donate_amount:")
    )
    application.add_handler(CommandHandler("donate", donate))
    application.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    application.add_handler(
        MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback)
    )
    for handler in handlers:
        application.add_handler(handler)
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message)
    )
    application.add_error_handler(error_handler)
    logger.info("🚀 Bot starting...")
    try:
        await application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
            close_loop=False,
        )
    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        if db.pool:
            await db.pool.close()


if __name__ == "__main__":
    asyncio.run(main())
