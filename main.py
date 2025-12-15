import logging
import random
import os
from typing import Dict
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from const import (
    dotaImages,
    namesDota,
    MODE_CLASH,
    MODE_DOTA,
    WORDS_CLASH,
    CARDS_CLASH,
)
from dotenv import load_dotenv

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)
load_dotenv()
rooms: Dict[str, Dict] = {}
user_rooms: Dict[int, str] = {}

DEFAULT_MODE = MODE_CLASH


def get_words_and_cards_by_mode(mode: str):
    if mode == MODE_DOTA:
        return namesDota, dotaImages
    return WORDS_CLASH, CARDS_CLASH


def get_mode_for_user(user_id: int) -> str:
    if user_id in user_rooms:
        room_id = user_rooms[user_id]
        room = rooms.get(room_id)
        if room is not None:
            return room.get("mode", DEFAULT_MODE)
    return DEFAULT_MODE


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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = get_main_keyboard()
    mode = get_mode_for_user(update.effective_user.id)
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


async def rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = get_main_keyboard()
    mode = get_mode_for_user(update.effective_user.id)
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


async def show_cards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    mode = get_mode_for_user(user_id)
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

    if user_id in user_rooms:
        keyboard = get_room_keyboard()
    else:
        keyboard = get_main_keyboard()

    await update.message.reply_text(response, reply_markup=keyboard)


async def create_room(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_type = update.effective_chat.type

    if chat_type != "private":
        await update.message.reply_text("❌ Создавать комнаты можно только в личном чате с ботом!")
        return

    room_id = str(random.randint(1000, 9999))
    while room_id in rooms:
        room_id = str(random.randint(1000, 9999))

    rooms[room_id] = {
        "creator": user_id,
        "mode": DEFAULT_MODE,
        "players": [user_id],
        "spy": None,
        "word": None,
        "card": None,
        "game_started": False,
        "players_data": {user_id: {"role": None, "word": None, "card": None}}
    }

    user_rooms[user_id] = room_id

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
        parse_mode="HTML",
        reply_markup=keyboard
    )


async def join_room(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_type = update.effective_chat.type

    if chat_type != "private":
        await update.message.reply_text("❌ Присоединяться к комнатам можно только в личном чате с ботом!")
        return

    if update.message.text == "🔗 Присоединиться":
        await update.message.reply_text("📝 Введите ID комнаты для присоединения:")
        return

    if len(context.args) == 0 and update.message.text != "🔗 Присоединиться":
        if update.message.text and update.message.text.isdigit():
            room_id = update.message.text
        else:
            await update.message.reply_text(
                "❌ Использование: /join <ID_комнаты> или отправьте ID комнаты после нажатия кнопки")
            return
    else:
        room_id = context.args[0]

    if room_id not in rooms:
        await update.message.reply_text("❌ Комната не найдена!")
        return

    room = rooms[room_id]

    if room["game_started"]:
        await update.message.reply_text("❌ Игра уже началась!")
        return

    if user_id in room["players"]:
        await update.message.reply_text("❌ Вы уже в этой комнате!")
        return

    if len(room["players"]) >= 15:
        await update.message.reply_text("❌ Комната переполнена!")
        return

    room["players"].append(user_id)
    room["players_data"][user_id] = {"role": None, "word": None, "card": None}
    user_rooms[user_id] = room_id

    keyboard = get_room_keyboard()
    await update.message.reply_text(
        f"✅ Вы присоединились к комнате {room_id}!\n\n"
        f"👥 Игроков: {len(room['players'])}/15\n"
        f"Ожидайте начала игры...",
        reply_markup=keyboard
    )

    try:
        await context.bot.send_message(
            room["creator"],
            f"📢 Игрок присоединился! Теперь игроков: {len(room['players'])}"
        )
    except:
        pass


async def start_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in user_rooms:
        await update.message.reply_text("❌ Вы не в комнате!")
        return

    room_id = user_rooms[user_id]
    room = rooms[room_id]
    mode = room.get("mode", DEFAULT_MODE)

    if room["creator"] != user_id:
        await update.message.reply_text("❌ Только создатель комнаты может начать игру!")
        return

    if len(room["players"]) < 2:
        await update.message.reply_text("❌ Нужно минимум 2 игрока!")
        return

    mode = room.get("mode", DEFAULT_MODE)
    words, cards_map = get_words_and_cards_by_mode(mode)

    word = random.choice(words)
    card_url = cards_map.get(word, "")
    spy = random.choice(room["players"])

    room["word"] = word
    room["card"] = card_url
    room["spy"] = spy
    room["game_started"] = True

    for player_id in room["players"]:
        if player_id == spy:
            room["players_data"][player_id]["role"] = "шпион"
            room["players_data"][player_id]["word"] = None
            room["players_data"][player_id]["card"] = None

            try:
                await context.bot.send_photo(
                    chat_id=player_id,
                    photo="https://i.pinimg.com/originals/41/15/70/4115707ee950d4b0aba69664f7986ae5.png",
                    caption=f"🎭 Вы - ШПИОН!\n\n"
                            f"❌ Вы не знаете слово!\n"
                            f"🎯 Ваша задача - понять, какое слово загадано.\n"
                            f"👥 Игроков в комнате: {len(room['players'])}\n\n"
                            f"💡 Подсказка: это объект из игры {get_theme_name(mode)}\n"
                            f"Посмотреть все варианты: /cards или кнопка '🎴 Все карты'"
                )
            except Exception as e:
                logger.error(f"Ошибка отправки фото шпиону: {e}")
                await context.bot.send_message(
                    player_id,
                    f"🎭 Вы - ШПИОН!\n\n"
                    f"❌ Вы не знаете слово!\n"
                    f"🎯 Ваша задача - понять, какое слово загадано.\n"
                    f"👥 Игроков в комнате: {len(room['players'])}"
                )
        else:
            room["players_data"][player_id]["role"] = "мирный"
            room["players_data"][player_id]["word"] = word
            room["players_data"][player_id]["card"] = card_url

            if card_url:
                try:
                    await context.bot.send_photo(
                        chat_id=player_id,
                        photo=card_url,
                        caption=f"✅ Вы - мирный игрок!\n\n"
                                f"🎴 Загаданная карта: <b>{word}</b>\n"
                                f"👥 Игроков в комнате: {len(room['players'])}\n"
                                f"⚠️ Среди вас есть шпион!",
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.error(f"Ошибка отправки фото мирному игроку: {e}")
                    await context.bot.send_message(
                        player_id,
                        f"✅ Вы - мирный игрок!\n\n"
                        f"🎴 Загаданная карта: {word}\n"
                        f"👥 Игроков в комнате: {len(room['players'])}\n"
                        f"⚠️ Среди вас есть шпион!"
                    )
            else:
                await context.bot.send_message(
                    player_id,
                    f"✅ Вы - мирный игрок!\n\n"
                    f"🎴 Загаданная карта: <b>{word}</b>\n"
                    f"👥 Игроков в комнате: {len(room['players'])}\n"
                    f"⚠️ Среди вас есть шпион!\n\n"
                    f"ℹ️ Для этой карты нет изображения",
                    parse_mode="HTML"
                )

    for player_id in room["players"]:
        try:
            await context.bot.send_message(
                player_id,
                f"🎮 Игра началась!\n"
                f"👥 Игроков: {len(room['players'])}\n"
                f"🎴 Тема: {get_theme_name(mode)}\n\n"
                f"🔍 Шпион не знает слово, остальные видят карту.\n"
                f"💬 Можно начинать обсуждение!\n\n"
                f"📌 Чтобы посмотреть свою роль и карту, нажмите /word"
            )
        except:
            pass


async def restart_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in user_rooms:
        await update.message.reply_text("❌ Вы не в комнате!")
        return

    room_id = user_rooms[user_id]
    room = rooms[room_id]

    if room["creator"] != user_id:
        await update.message.reply_text("❌ Только создатель комнаты может перезапустить игру!")
        return

    room["spy"] = None
    room["word"] = None
    room["card"] = None
    room["game_started"] = False

    for player_id in room["players_data"]:
        room["players_data"][player_id]["role"] = None
        room["players_data"][player_id]["word"] = None
        room["players_data"][player_id]["card"] = None

    mode = room.get("mode", DEFAULT_MODE)
    words, _ = get_words_and_cards_by_mode(mode)

    keyboard = get_room_keyboard()
    await update.message.reply_text(
        f"🔄 Игра перезапущена!\n\n"
        f"ID комнаты: <code>{room_id}</code>\n"
        f"👥 Игроков: {len(room['players'])}\n"
        f"🎴 Режим: {get_theme_name(mode)}\n"
        f"Доступно слов: {len(words)}\n"
        f"Создатель комнаты может сменить режим командами /mode_clash и /mode_dota\n\n"
        f"Для начала новой игры нажмите '▶️ Начать игру'",
        parse_mode="HTML",
        reply_markup=keyboard
    )

    for player_id in room["players"]:
        if player_id != user_id:
            try:
                await context.bot.send_message(
                    player_id,
                    f"🔄 Создатель перезапустил игру!\n"
                    f"Ожидайте начала новой игры."
                )
            except:
                pass


async def get_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_type = update.effective_chat.type

    if chat_type != "private":
        await update.message.reply_text("❌ Эта команда работает только в личном чате с ботом!")
        return

    if user_id not in user_rooms:
        await update.message.reply_text("❌ Вы не в игре!")
        return

    room_id = user_rooms[user_id]
    room = rooms[room_id]

    if not room["game_started"]:
        await update.message.reply_text("❌ Игра ещё не началась!")
        return

    player_data = room["players_data"][user_id]

    if player_data["role"] == "шпион":
        try:
                await context.bot.send_photo(
                    chat_id=user_id,
                    photo="https://static.wikia.nocookie.net/clashroyale/images/4/4e/SkeletonsCard.png/revision/latest?cb=20160120012747&path-prefix=ru",
                    caption=(
                        "🎭 Вы - ШПИОН!\n\n"
                        "❌ Вы не знаете слово!\n"
                        "🎯 Ваша задача - понять, какое слово загадано.\n"
                        "👥 Игроков в комнате: {}\n\n"
                        "💡 Подсказка: это объект из игры {}\n"
                        "Посмотреть все варианты: /cards"
                    ).format(len(room['players']), get_theme_name(mode))
                )
        except:
            await update.message.reply_text(
                (
                    "🎭 Вы - ШПИОН!\n\n"
                    "❌ Вы не знаете слово!\n"
                    "🎯 Ваша задача - понять, какое слово загадано.\n"
                    "👥 Игроков в комнате: {}\n\n"
                    "💡 Подсказка: это объект из игры {}\n"
                    "Посмотреть все варианты: /cards"
                ).format(len(room['players']), get_theme_name(mode))
            )
    else:
        if player_data["card"]:
            try:
                await context.bot.send_photo(
                    chat_id=user_id,
                    photo=player_data["card"],
                    caption=f"✅ Вы - мирный игрок!\n\n"
                            f"🎴 Загаданная карта: <b>{player_data['word']}</b>\n"
                            f"👥 Игроков в комнате: {len(room['players'])}\n"
                            f"⚠️ Среди вас есть шпион!",
                    parse_mode="HTML"
                )
            except:
                await update.message.reply_text(
                    f"✅ Вы - мирный игрок!\n\n"
                    f"🎴 Загаданная карта: {player_data['word']}\n"
                    f"👥 Игроков в комнате: {len(room['players'])}\n"
                    f"⚠️ Среди вас есть шпион!"
                )
        else:
            await update.message.reply_text(
                f"✅ Вы - мирный игрок!\n\n"
                f"🎴 Загаданная карта: <b>{player_data['word']}</b>\n"
                f"👥 Игроков в комнате: {len(room['players'])}\n"
                f"⚠️ Среди вас есть шпион!\n\n"
                f"ℹ️ Для этой карты нет изображения",
                parse_mode="HTML"
            )


async def show_players(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in user_rooms:
        await update.message.reply_text("❌ Вы не в комнате!")
        return

    room_id = user_rooms[user_id]
    room = rooms[room_id]
    mode = room.get("mode", DEFAULT_MODE)

    players_list = ""
    for i, player_id in enumerate(room["players"]):
        role = room["players_data"][player_id]["role"]
        if role:
            players_list += f"• Игрок {i + 1} ({role})\n"
        else:
            players_list += f"• Игрок {i + 1}\n"

    status = "🎮 Игра начата" if room["game_started"] else "⏳ Ожидание"
    current_word = f"\n🎴 Текущее слово: {room['word']}" if room["word"] else ""

    await update.message.reply_text(
        f"👥 Комната {room_id}:\n\n"
        f"Игроков: {len(room['players'])}\n"
        f"Режим: {get_theme_name(mode)}\n"
        f"Статус: {status}{current_word}\n\n"
        f"{players_list}"
    )


async def leave_room(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in user_rooms:
        await update.message.reply_text("❌ Вы не в комнате!")
        return

    room_id = user_rooms[user_id]
    room = rooms[room_id]

    if user_id in room["players"]:
        room["players"].remove(user_id)

    if user_id in room["players_data"]:
        del room["players_data"][user_id]

    del user_rooms[user_id]

    if not room["players"]:
        del rooms[room_id]
    else:
        if room["creator"] == user_id:
            room["creator"] = room["players"][0]
            try:
                await context.bot.send_message(
                    room["creator"],
                    f"👑 Вы стали новым создателем комнаты {room_id}!"
                )
            except:
                pass

    keyboard = get_main_keyboard()
    await update.message.reply_text(
        "✅ Вы вышли из комнаты!",
        reply_markup=keyboard
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


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(msg="Exception while handling an update:", exc_info=context.error)


async def set_mode_clash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in user_rooms:
        await update.message.reply_text("❌ Сначала создайте комнату /create, чтобы выбрать режим!")
        return

    room_id = user_rooms[user_id]
    room = rooms[room_id]

    if room["creator"] != user_id:
        await update.message.reply_text("❌ Только создатель комнаты может менять режим!")
        return

    if room["game_started"]:
        await update.message.reply_text("❌ Нельзя менять режим во время игры!")
        return

    room["mode"] = MODE_CLASH
    words, _ = get_words_and_cards_by_mode(MODE_CLASH)

    await update.message.reply_text(
        f"✅ Режим изменён на {get_theme_name(MODE_CLASH)}.\n"
        f"Доступно слов: {len(words)}"
    )


async def set_mode_dota(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in user_rooms:
        await update.message.reply_text("❌ Сначала создайте комнату /create, чтобы выбрать режим!")
        return

    room_id = user_rooms[user_id]
    room = rooms[room_id]

    if room["creator"] != user_id:
        await update.message.reply_text("❌ Только создатель комнаты может менять режим!")
        return

    if room["game_started"]:
        await update.message.reply_text("❌ Нельзя менять режим во время игры!")
        return

    room["mode"] = MODE_DOTA
    words, _ = get_words_and_cards_by_mode(MODE_DOTA)

    await update.message.reply_text(
        f"✅ Режим изменён на {get_theme_name(MODE_DOTA)}.\n"
        f"Доступно героев: {len(words)}"
    )


def main():
    API_TOKEN = os.getenv('API_TOKEN')
    if API_TOKEN == "ВАШ_API_КЛЮЧ":
        print("ЗАМЕНИТЕ 'ВАШ_API_КЛЮЧ' НА ВАШ ТОКЕН!")
        return

    application = Application.builder().token(API_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("create", create_room))
    application.add_handler(CommandHandler("join", join_room))
    application.add_handler(CommandHandler("startgame", start_game))
    application.add_handler(CommandHandler("restart", restart_game))
    application.add_handler(CommandHandler("word", get_word))
    application.add_handler(CommandHandler("players", show_players))
    application.add_handler(CommandHandler("leave", leave_room))
    application.add_handler(CommandHandler("rules", rules))
    application.add_handler(CommandHandler("cards", show_cards))
    application.add_handler(CommandHandler("mode_clash", set_mode_clash))
    application.add_handler(CommandHandler("mode_dota", set_mode_dota))
    application.add_handler(CommandHandler("help", start))
    application.add_handler(CommandHandler("menu", start))

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    application.add_error_handler(error_handler)

    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
