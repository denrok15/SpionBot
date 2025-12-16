from telegram.ext import ContextTypes
from telegram import Update
from main import decorators
from utils.other import get_theme_name,get_words_and_cards_by_mode
from handlers.button import get_room_keyboard,get_main_keyboard
import random
from telegram.constants import ParseMode
from utils.decorators import logger,room_locks
from database.crud import db
from const import (
    dotaImages,
    namesDota,
    MODE_CLASH,
    MODE_DOTA,
    WORDS_CLASH,
    CARDS_CLASH,
)
DEFAULT_MODE = MODE_CLASH
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
        players_list += f"• Игрок {i + 1} ({role})\n"

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
