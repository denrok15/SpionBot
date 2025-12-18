import random
from const import (
    MODE_CLASH,
    MODE_DOTA,
)
from telegram import Update, LabeledPrice
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import ContextTypes
from utils.decorators import create_decorators
from database.actions import db
from handlers.button import get_main_keyboard, get_room_keyboard
from utils.decorators import logger, room_locks, subscription_required
from utils.gameMod import get_theme_name, get_words_and_cards_by_mode
from utils.subscription import is_subscribed, subscribe_keyboard

DEFAULT_MODE = MODE_CLASH

decorators = create_decorators(db)

async def show_main_menu(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    keyboard = get_main_keyboard()

    room_id = await db.get_user_room(user_id)
    if room_id:
        room = await db.get_room(room_id)
        mode = room.get("mode", DEFAULT_MODE) if room else DEFAULT_MODE
    else:
        mode = DEFAULT_MODE

    theme_name = get_theme_name(mode)
    await context.bot.send_message(
    chat_id=user_id,
    text=(
        f"<b>🎮 Добро пожаловать в игру 'Шпион'!</b>\n\n"
        f"📌 <b>Команды для начала:</b>\n"
        f"• /create — создать комнату\n"
        f"• /join &lt;ID комнаты&gt; — присоединиться к комнате\n"
        f"• /startgame — начать игру\n\n"
        f"🎴 <b>Текущая тематика:</b> {theme_name}\n"
        f"👑 Игру создали It tut Денис и Артур!"
    ),
    parse_mode=ParseMode.HTML,
    reply_markup=keyboard
)
    
async def check_subscription_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
)->None:
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()
    if await is_subscribed(context.bot, user_id):
        await query.message.delete()
        await show_main_menu(user_id, context)
    else:
        new_text = "❌ Ты ещё не подписался на канал. Подпишись, чтобы продолжить:"
        new_markup = subscribe_keyboard()
        if query.message.text != new_text or query.message.reply_markup != new_markup:
            try:
                await query.message.edit_text(new_text, reply_markup=new_markup)
            except BadRequest:
                pass

@decorators.rate_limit()
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE)->None:
    user_id = update.effective_user.id
    if not await is_subscribed(context.bot, user_id):
        await update.message.reply_text(
            "❗ Чтобы играть, подпишись на канал:", reply_markup=subscribe_keyboard()
        )
        return
    await show_main_menu(user_id, context)


@subscription_required
@decorators.rate_limit()
@decorators.private_chat_only()
async def create_room(update: Update, context: ContextTypes.DEFAULT_TYPE)->None:
    user_id = update.effective_user.id
    for _ in range(10):
        room_id = str(random.randint(1000, 9999))
        room = await db.get_room(room_id)
        if not room:
            break
    else:
        await update.message.reply_text(
            "❌ Не удалось создать комнату. Попробуйте ещё раз."
        )
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
        reply_markup=keyboard,
    )


@subscription_required
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
            await update.message.reply_text(
                "❌ Использование: /join <ID_комнаты> или отправьте ID комнаты"
            )

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

        if current_room:
            if current_room == room_id:
                await update.message.reply_text("❌ Вы уже в этой комнате!")

                return

            await update.message.reply_text(
                "❌ Сначала выйдите из текущей комнаты, чтобы присоединиться к другой."
            )

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
        reply_markup=keyboard,
    )

    creator_id = room["creator_id"]

    try:
        await context.bot.send_message(
            creator_id, f"📢 Игрок присоединился! Теперь игроков: {len(players)}"
        )

    except:
        pass

@decorators.game_not_started()
@subscription_required
@decorators.rate_limit()
@decorators.creator_only()
@decorators.room_lock()
async def start_game(update: Update, context: ContextTypes.DEFAULT_TYPE)->None:
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
                        caption=f"🎭 Вы - ШПИОН!\n\n❌ Вы не знаете слово!\n🎯 Ваша задача - понять слово.\n👥 Игроков: {len(players)}\n\n💡 Подсказка: это объект из {get_theme_name(mode)}",
                    )

                else:
                    result = await context.bot.send_photo(
                        chat_id=player_id,
                        photo="https://i.pinimg.com/originals/41/15/70/4115707ee950d4b0aba69664f7986ae5.png",
                        caption=f"🎭 Вы - ШПИОН!\n\n❌ Вы не знаете слово!\n🎯 Ваша задача - понять слово.\n👥 Игроков: {len(players)}\n\n💡 Подсказка: это объект из {get_theme_name(mode)}",
                    )

                    if hasattr(result, "photo") and result.photo:
                        await db.cache_image(
                            "https://i.pinimg.com/originals/41/15/70/4115707ee950d4b0aba69664f7986ae5.png",
                            result.photo[-1].file_id,
                            mode,
                        )

            except Exception as e:
                logger.error(f"Error sending spy photo: {e}")

                await context.bot.send_message(
                    player_id,
                    f"🎭 Вы - ШПИОН!\n\n❌ Вы не знаете слово!\n🎯 Ваша задача - понять слово.\n👥 Игроков: {len(players)}",
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
                            parse_mode=ParseMode.HTML,
                        )

                    else:
                        result = await context.bot.send_photo(
                            chat_id=player_id,
                            photo=card_url,
                            caption=f"✅ Вы - мирный игрок!\n\n🎴 Загаданная карта: <b>{word}</b>\n👥 Игроков: {len(players)}\n⚠️ Среди вас есть шпион!",
                            parse_mode=ParseMode.HTML,
                        )

                        if hasattr(result, "photo") and result.photo:
                            await db.cache_image(
                                card_url, result.photo[-1].file_id, mode
                            )

                except Exception as e:
                    logger.error(f"Error sending card photo: {e}")

                    await context.bot.send_message(
                        player_id,
                        f"✅ Вы - мирный игрок!\n\n🎴 Загаданная карта: <b>{word}</b>\n👥 Игроков: {len(players)}\n⚠️ Среди вас есть шпион!",
                        parse_mode=ParseMode.HTML,
                    )

            else:
                await context.bot.send_message(
                    player_id,
                    f"✅ Вы - мирный игрок!\n\n🎴 Загаданная карта: <b>{word}</b>\n👥 Игроков: {len(players)}\n⚠️ Среди вас есть шпион!",
                    parse_mode=ParseMode.HTML,
                )

    for player_id in players:
        try:
            await context.bot.send_message(
                player_id,
                f"🎮 Игра началась!\n👥 Игроков: {len(players)}\n🎴 Тема: {get_theme_name(mode)}\n\n💬 Можно начинать обсуждение!",
            )

        except:
            pass


@subscription_required
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
        reply_markup=keyboard,
    )

    for player_id in players:
        if player_id != user_id:
            try:
                await context.bot.send_message(
                    player_id,
                    "🔄 Создатель перезапустил игру!\nОжидайте начала новой игры.",
                )

            except:
                pass


@subscription_required
@decorators.rate_limit()
@decorators.private_chat_only()
@decorators.rate_limit()
@decorators.private_chat_only()
async def get_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

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
                    caption=f"🎭 Вы - ШПИОН!\n\n❌ Вы не знаете слово!\n👥 Игроков: {len(await db.get_room_players(room_id))}",
                )

            else:
                await context.bot.send_photo(
                    chat_id=user_id,
                    photo="https://i.pinimg.com/originals/41/15/70/4115707ee950d4b0aba69664f7986ae5.png",
                    caption=f"🎭 Вы - ШПИОН!\n\n❌ Вы не знаете слово!\n👥 Игроков: {len(await db.get_room_players(room_id))}",
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
                        parse_mode=ParseMode.HTML,
                    )

                else:
                    await context.bot.send_photo(
                        chat_id=user_id,
                        photo=player_data["card_url"],
                        caption=f"✅ Вы - мирный игрок!\n\n🎴 Загаданная карта: <b>{player_data['word']}</b>\n👥 Игроков: {len(await db.get_room_players(room_id))}",
                        parse_mode=ParseMode.HTML,
                    )

            except:
                await update.message.reply_text(
                    f"✅ Вы - мирный игрок!\n\n🎴 Загаданная карта: <b>{player_data['word']}</b>\n👥 Игроков: {len(await db.get_room_players(room_id))}",
                    parse_mode=ParseMode.HTML,
                )

        else:
            await update.message.reply_text(
                f"✅ Вы - мирный игрок!\n\n🎴 Загаданная карта: <b>{player_data['word']}</b>\n👥 Игроков: {len(await db.get_room_players(room_id))}",
                parse_mode=ParseMode.HTML,
            )


@subscription_required
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


@subscription_required
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
                    players[0], f"👑 Вы стали новым создателем комнаты {room_id}!"
                )

            except:
                pass
        if len(players) == 1:
            await db.reset_room_game(room_id)

            try:
                await context.bot.send_message(
                    players[0],
                    "⚠️ В комнате остался только один игрок, игра остановлена. "
                    "Когда появятся новые участники, нажмите ▶️ Начать игру.",
                )

            except:
                pass

    await db.remove_player_from_all_rooms(user_id)
    keyboard = get_main_keyboard()

    await update.message.reply_text("✅ Вы вышли из комнаты!", reply_markup=keyboard)


@subscription_required
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
    "🕵️ *Игра «Шпион» — правила*\n\n"

    "👥 *Роли*\n\n"
    "• 🧑‍🤝‍🧑 Все игроки, кроме одного, получают *одно и то же слово*\n"
    "• 🕶️ *Шпион* — единственный, кто *не знает слово*\n\n"

    "🗣️ *Ход игры*\n\n"
    "1️⃣ Игроки по очереди задают вопросы о загаданном слове\n"
    "2️⃣ Вопросы должны помогать определить, кто шпион\n"
    "3️⃣ Отвечать нужно честно, *не называя слово напрямую*\n\n"

    "🎯 *Цели*\n\n"
    "• 🕶️ *Шпион*: понять, какое слово загадано\n"
    "• 🧑‍🤝‍🧑 *Остальные игроки*: вычислить шпиона\n\n"

    f"🎴 *Тематика*: {theme_name}\n"
    "🖼️ Каждому слову соответствует объект из выбранной игры\n\n"

    "ℹ️ *Важно*\n\n"
    "Игра проходит *устно* — бот только раздаёт роли и управляет игрой\n\n"
    "Удачной игры и приятного разоблачения 😈",
    parse_mode=ParseMode.MARKDOWN,
    reply_markup=keyboard,
)



@subscription_required
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
        response += (
            "📸 Карты с изображениями:\n" + "\n".join(cards_with_images[:10]) + "\n\n"
        )

    if cards_without_images:
        response += (
            "🖼️ Карты без изображений:\n" + "\n".join(cards_without_images[:10]) + "\n\n"
        )

    if len(cards_with_images) + len(cards_without_images) > 20:
        response += f"... и ещё {len(words) - 20} вариантов\n\n"

    response += f"Всего вариантов: {len(words)}\n"

    response += f"С изображениями: {len(cards_with_images)}\n"

    response += f"Без изображений: {len(cards_without_images)}"

    await update.message.reply_text(response, reply_markup=keyboard)


@subscription_required
@decorators.rate_limit()
@decorators.private_chat_only()
@decorators.creator_only()
@decorators.room_lock()
async def set_mode_clash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    room_id = await db.get_user_room(user_id)

    if not room_id:
        await update.message.reply_text(
            "❌ Сначала создайте комнату /create, чтобы выбрать режим!"
        )

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


@subscription_required
@decorators.rate_limit()
@decorators.private_chat_only()
@decorators.creator_only()
@decorators.room_lock()
async def set_mode_dota(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    room_id = await db.get_user_room(user_id)

    if not room_id:
        await update.message.reply_text(
            "❌ Сначала создайте комнату /create, чтобы выбрать режим!"
        )

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


@subscription_required
@decorators.rate_limit()
async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    room_id = await db.get_user_room(user_id)

    if room_id:
        player_data = await db.get_player_data(user_id, room_id)

        if player_data:
            players = await db.get_room_players(room_id)

            room = await db.get_room(room_id)

            await update.message.reply_text(
                f"📊 Статистика комнаты {room_id}:\n\n"
                f"👥 Игроков: {len(players)}\n"
                f"🎯 Режим: {get_theme_name(room['mode'])}\n"
                f"🎮 Игра начата: {'Да' if room['game_started'] else 'Нет'}\n"
                f"📅 Создана: {room['created_at'].strftime('%Y-%m-%d %H:%M')}"
            )
            return

    stats = await db.get_all_rooms_stats()
    await update.message.reply_text(
        f"📊 Общая статистика бота:\n\n"
        f"🏠 Всего комнат: {stats['total_rooms']}\n"
        f"🎮 Активных игр: {stats['active_rooms']}\n"
        f"👤 Всего игроков: {stats['total_players']}"
    )

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    # user_id = update.effective_user.id не используется в функции

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
        user_id = update.effective_user.id
        room_id = await db.get_user_room(user_id)

        if room_id:
            await leave_room(update, context)

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

async def donate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Отправляет пользователю инвойс для доната через Telegram Stars (XTR)
    """
    prices = [LabeledPrice(label="Поддержка автора", amount=100)]
    await context.bot.send_invoice(
        chat_id=update.effective_chat.id,
        title="Поддержка автора",
        description="Спасибо за поддержку! Каждая звезда помогает развивать бота.",
        payload="donate_payload",
        currency="XTR",
        prices=prices,
        start_parameter="donate",
        provider_token="",
    )


async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Telegram присылает pre_checkout_query перед оплатой.
    Нужно подтвердить, что платеж можно принять
    """
    query = update.pre_checkout_query
    await query.answer(ok=True)


async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    После успешной оплаты можно поблагодарить пользователя
    """
    payment = update.message.successful_payment
    await update.message.reply_text(
        f"Спасибо за поддержку! Вы пожертвовали {payment.total_amount / 100} звёзд."
    )
