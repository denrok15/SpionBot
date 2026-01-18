import random
import asyncio
import html
from dataclasses import dataclass,field
from datetime import datetime, timezone, timedelta
from io import BytesIO
from pathlib import Path
from typing import Dict, Optional

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile,
    InputMediaPhoto,
    LabeledPrice,
    Update,
)
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from const import MODE_BRAWL, MODE_CLASH, MODE_DOTA
from database.actions import db
from handlers.button import (
    get_main_keyboard,
    get_admin_panel_keyboard,
    get_room_keyboard,
    get_room_mode_keyboard,
    get_restart_room_text,
    get_join_room_text,
    build_spy_count_keyboard,
    _build_cabinet_keyboard,
    _build_hint_selection_keyboard,
    _personal_account_text,
    _build_donate_keyboard
)
from utils.decorators import (
    create_decorators,
    logger,
    room_locks,
    subscription_required,
)
from handlers.button import get_inline_keyboard,get_game_inline_button,get_message_start
from utils.gameMod import get_theme_name, get_words_and_cards_by_mode
from utils.subscription import is_subscribed, subscribe_keyboard
from const import MODE_SELECTION_LABELS,MODE_ENTITY_LABELS,HINT_PRICES,HINT_LABELS,HINT_QUANTITIES,ADMIN
DEFAULT_MODE = MODE_CLASH

decorators = create_decorators(db)



SINGLE_MODE_PLACEHOLDER_URL = (
    "https://via.placeholder.com/512x512.png?text=Spy+Mode"
)
BACK_CARD_PATH = Path("static/backCard.png")
BACK_CARD_BYTES = BACK_CARD_PATH.read_bytes() if BACK_CARD_PATH.exists() else None
SPY_CARD_PATH = Path("static/SpionCard.png")
SPY_CARD_BYTES = SPY_CARD_PATH.read_bytes() if SPY_CARD_PATH.exists() else None
SPY_CARD_CACHE_KEY = f"static:{SPY_CARD_PATH.as_posix()}"
SINGLE_MODE_PLAYER_OPTIONS = [2, 3, 4, 5, 6, 7, 8, 9, 10]
SINGLE_MODE_SPY_IMAGE_URL = (
    "https://i.pinimg.com/originals/41/15/70/4115707ee950d4b0aba69664f7986ae5.png"
)

TZ_MSK_PLUS_4 = timezone(timedelta(hours=7))
@dataclass
class SingleModeSession:
    chat_id: int
    message_id: int
    word: str
    card_url: str
    player_count: int
    spy_count: int
    spy_indices: tuple[int, ...]
    current_index: int
    mode: str
    revealed: bool = False
    back_card_file_id: Optional[str] = None
    spy_card_file_id: Optional[str] = None
    time: datetime = field(default_factory=lambda: datetime.now(TZ_MSK_PLUS_4))

SINGLE_MODE_SESSIONS: Dict[int, SingleModeSession] = {}

MAX_ROOM_CHAT_LEN = 800


async def show_main_menu(
    user_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    notice: Optional[str] = None,
):
    if user_id in ADMIN:
        keyboard = get_main_keyboard("😈 Админ Панель")
    else:
        keyboard = get_main_keyboard()

    room_id = await db.get_user_room(user_id)
    if room_id:
        room = await db.get_room(room_id)
        mode = room.get("mode", DEFAULT_MODE) if room else DEFAULT_MODE
    else:
        mode = DEFAULT_MODE

    theme_name = get_theme_name(mode)
    base_text = (
        f"<b>🎮 Добро пожаловать в игру 'Шпион'!</b>\n\n"
        f"📌 <b>Команды для начала:</b>\n"
        f"• /create — создать комнату\n"
        f"• /join &lt;ID комнаты&gt; — присоединиться к комнате\n"
        f"• /startgame — начать игру\n"
        f"• /single — игра с 1 устройства\n\n"
        f"👑 Игру создали It tut Денис и Артур!"
    )
    text = f"{notice}\n\n{base_text}" if notice else base_text
    await context.bot.send_message(
        chat_id=user_id,
        text=text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )


def _get_display_name(user):
    if not user:
        return "Игрок"
    return user.full_name or user.username or "Игрок"


def _parse_referral_code(code: str) -> Optional[int]:
    if not code:
        return None
    normalized = code.strip().lower()
    if not normalized.startswith("ref"):
        return None
    remainder = normalized[3:].lstrip("-_")
    if not remainder.isdigit():
        return None
    inviter_id = int(remainder)
    if inviter_id <= 0:
        return None
    return inviter_id


def _get_user_display_for_chat(user) -> str:
    if not user:
        return "Игрок"
    return user.full_name or user.username or "Игрок"


async def _broadcast_room_chat(
    room_id: str,
    sender_id: int,
    sender_user,
    text: str,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not text:
        return
    message_text = text.strip()
    if not message_text:
        return
    if len(message_text) > MAX_ROOM_CHAT_LEN:
        message_text = message_text[:MAX_ROOM_CHAT_LEN] + "…"

    sender_name = _get_user_display_for_chat(sender_user)
    safe_sender = html.escape(sender_name)
    safe_text = html.escape(message_text)
    payload = f"💬 <b>{safe_sender}</b>: {safe_text}"

    players = await db.get_room_players(room_id)
    for player_id in players:
        if player_id == sender_id:
            continue
        try:
            await context.bot.send_message(
                chat_id=player_id,
                text=payload,
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            continue


async def _handle_referral_start(
    user_id: int,
    code: str,
    friend_name: str,
    context: ContextTypes.DEFAULT_TYPE,
) -> Optional[str]:
    inviter_id = _parse_referral_code(code)
    if not inviter_id or inviter_id == user_id:
        return None

    existing_inviter = await db.get_referrer(user_id)
    if existing_inviter:
        return None

    created = await db.create_referral(user_id, inviter_id)
    if not created:
        return None

    inviter_balance = await db.add_balance(inviter_id, 2)
    friend_balance = await db.add_balance(user_id, 1)

    friend_display = friend_name or "Друг"

    inviter_message = (
        f"🎉 {friend_display} присоединился по вашей реферальной ссылке и вы получили 2⭐!"
    )
    if inviter_balance is not None:
        inviter_message += f"\n⭐ Баланс: {inviter_balance}⭐"

    try:
        await context.bot.send_message(inviter_id, inviter_message)
    except Exception:
        pass

    friend_message = "🎉 Вы получили 1⭐ за регистрацию по реферальной ссылке!"
    if friend_balance is not None:
        friend_message += f"\n⭐ Баланс: {friend_balance}⭐"
    return friend_message


def _build_single_mode_selection_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for i in range(0, len(SINGLE_MODE_PLAYER_OPTIONS), 3):
        buttons = [
            InlineKeyboardButton(
                f"{count} игроков", callback_data=f"single:select:{count}"
            )
            for count in SINGLE_MODE_PLAYER_OPTIONS[i : i + 3]
        ]
        rows.append(buttons)
    rows.append(
        [InlineKeyboardButton("❌ Отмена", callback_data="single:cancel")]
    )
    return InlineKeyboardMarkup(rows)



def _build_single_mode_keyboard(session: SingleModeSession) -> InlineKeyboardMarkup:
    is_spy = session.current_index in session.spy_indices
    if session.revealed and is_spy:
        center_label = "Вы — шпион"
    else:
        center_label = session.word if session.revealed else "Карта скрыта"
    reveal_label = "🔓 Скрыть карту" if session.revealed else "🃏 Открыть карту"
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("⬅️", callback_data="single:prev"),
                InlineKeyboardButton(center_label, callback_data="single:noop"),
                InlineKeyboardButton("➡️", callback_data="single:next"),
            ],
            [
                InlineKeyboardButton(reveal_label, callback_data="single:reveal"),
                InlineKeyboardButton("🏠 Главное меню", callback_data="single:exit"),
            ],
            [
                InlineKeyboardButton(
                    f"🕵️ Шпионов: {session.spy_count}", callback_data="single:spy_menu"
                )
            ],
            [
                InlineKeyboardButton("🔁 Перезапустить", callback_data="single:restart")
            ],
        ]
    )


def _build_single_mode_caption(session: SingleModeSession) -> str:
    is_spy = session.current_index in session.spy_indices
    if not session.revealed:
        theme_name = get_theme_name(session.mode)
        return (
            f"🎴 Карта скрыта\n"
            f"🎯 Тематика: {theme_name}\n"
            f"🕵️ Шпионов: {session.spy_count}\n"
            "📱 Передайте телефон следующему игроку, затем нажмите «Открыть карту».\n"
            f"Игрок {session.current_index + 1}/{session.player_count}"
        )
    if is_spy:
        return (
            f"🎭 Вы — шпион!\n"
            "❌ Вы не знаете слово, но наблюдайте за реакциями остальных.\n"
            f"Игрок {session.current_index + 1}/{session.player_count}"
        )
    theme_name = get_theme_name(session.mode)
    return (
        f"✅ Вы мирный игрок!\n"
        f"🎴 Слово: <b>{session.word}</b>\n"
        f"🎯 Тематика: {theme_name}\n"
        f"⚠️ Все остальные тоже видят это слово."
        f"\nИгрок {session.current_index + 1}/{session.player_count}"
    )


def _create_single_mode_session(
    player_count: int, mode: str, spy_count: int = 1
) -> Optional[SingleModeSession]:
    words, cards_map = get_words_and_cards_by_mode(mode)
    if not words:
        return None
    if not isinstance(spy_count, int) or spy_count < 1:
        spy_count = 1
    max_spies = max(1, player_count - 1)
    spy_count = min(spy_count, max_spies)
    word = random.choice(words)
    card_url = cards_map.get(word, "")
    spy_indices = tuple(sorted(random.sample(range(player_count), k=spy_count)))
    return SingleModeSession(
        chat_id=0,
        message_id=0,
        word=word,
        card_url=card_url,
        player_count=player_count,
        spy_count=spy_count,
        spy_indices=spy_indices,
        current_index=0,
        mode=mode,
    )


def _build_single_mode_spy_selection_keyboard(
    player_count: int, callback_prefix: str, include_back: bool
) -> InlineKeyboardMarkup:
    max_spies = max(1, player_count - 1)
    options = list(range(1, min(5, max_spies) + 1))
    rows = []
    for i in range(0, len(options), 3):
        rows.append(
            [
                InlineKeyboardButton(
                    f"{count} шпион" if count == 1 else f"{count} шпиона",
                    callback_data=f"{callback_prefix}{count}",
                )
                for count in options[i : i + 3]
            ]
        )
    if include_back:
        rows.append([InlineKeyboardButton("⬅️ Назад", callback_data="single:back")])
    else:
        rows.append([InlineKeyboardButton("❌ Отмена", callback_data="single:cancel")])
    return InlineKeyboardMarkup(rows)


def _get_single_mode_photo(session: SingleModeSession):
    is_spy = session.current_index in session.spy_indices
    if session.revealed:
        if is_spy:
            if session.spy_card_file_id:
                return session.spy_card_file_id
            if SPY_CARD_BYTES:
                return InputFile(BytesIO(SPY_CARD_BYTES), filename=SPY_CARD_PATH.name)
            return SINGLE_MODE_SPY_IMAGE_URL
        return session.card_url or SINGLE_MODE_PLACEHOLDER_URL
    if session.back_card_file_id:
        return session.back_card_file_id
    if BACK_CARD_BYTES:
        return InputFile(BytesIO(BACK_CARD_BYTES), filename=BACK_CARD_PATH.name)
    return SINGLE_MODE_PLACEHOLDER_URL


async def _send_single_mode_card(
    user_id: int, context: ContextTypes.DEFAULT_TYPE, session: SingleModeSession
):
    photo_source = _get_single_mode_photo(session)
    try:
        message = await context.bot.send_photo(
            chat_id=user_id,
            photo=photo_source,
            caption=_build_single_mode_caption(session),
            parse_mode=ParseMode.HTML,
            reply_markup=_build_single_mode_keyboard(session),
        )
    except BadRequest as exc:
        logger.error("Single mode send failed: %s", exc)
        return await context.bot.send_message(
            chat_id=user_id,
            text=_build_single_mode_caption(session),
            parse_mode=ParseMode.HTML,
            reply_markup=_build_single_mode_keyboard(session),
        )
    if not session.back_card_file_id and hasattr(message, "photo") and message.photo:
        session.back_card_file_id = message.photo[-1].file_id
    if (
        session.revealed
        and session.current_index in session.spy_indices
        and not session.spy_card_file_id
        and hasattr(message, "photo")
        and message.photo
    ):
        session.spy_card_file_id = message.photo[-1].file_id
    return message


async def _update_single_mode_message(
    query, session: SingleModeSession
):
    if not query.message:
        return
    photo_source = _get_single_mode_photo(session)
    caption = _build_single_mode_caption(session)
    keyboard = _build_single_mode_keyboard(session)
    media = InputMediaPhoto(media=photo_source, caption=caption, parse_mode=ParseMode.HTML)
    try:
        result = await query.edit_message_media(media=media, reply_markup=keyboard)
        if (
            session.revealed
            and session.current_index in session.spy_indices
            and not session.spy_card_file_id
            and hasattr(result, "photo")
            and result.photo
        ):
            session.spy_card_file_id = result.photo[-1].file_id
    except BadRequest:
        try:
            await query.message.edit_caption(
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
            )
        except BadRequest as exc:
            logger.warning("Не удалось обновить Single Mode: %s", exc)


async def check_subscription_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
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
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    referral_notice = None
    message_text = (update.message.text or "").strip()
    command = message_text.split()[0] if message_text else ""
    if command.startswith("/start"):
        args = context.args or []
        if args:
            friend_name = _get_display_name(update.effective_user)
            referral_notice = await _handle_referral_start(
                user_id, args[0], friend_name, context
            )
    if not await is_subscribed(context.bot, user_id):
        if referral_notice:
            await update.message.reply_text(referral_notice)
        await update.message.reply_text(
            "❗ Чтобы играть, подпишись на канал:", reply_markup=subscribe_keyboard()
        )
        return
    await db.ensure_user_account(user_id)
    await show_main_menu(user_id, context, notice=referral_notice)


@subscription_required
@decorators.rate_limit()
@decorators.private_chat_only()
async def single_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    SINGLE_MODE_SESSIONS.pop(user_id, None)
    keyboard = _build_single_mode_selection_keyboard()
    await update.message.reply_text(
        "🃏 Выберите количество игроков",
        reply_markup=keyboard,
    )


@subscription_required
@decorators.rate_limit()
@decorators.private_chat_only()
async def create_room(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
    success = await db.create_room(room_id, user_id, DEFAULT_MODE, spy_count=1)

    if not success:
        await update.message.reply_text("❌ Ошибка при создании комнаты.")

        return

    words, _ = get_words_and_cards_by_mode(DEFAULT_MODE)

    keyboard = get_room_mode_keyboard()
    inline_keyboard = get_inline_keyboard('start_game')
    await update.message.reply_text(
        "✅ Комната создана!\n\n",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )
    await update.message.reply_text(
        text=get_message_start(room_id, 1, get_theme_name(DEFAULT_MODE), spy_count=1),
        parse_mode=ParseMode.HTML,
        reply_markup=inline_keyboard,
    )
    await update.message.reply_text(
        "🕵️ Выберите количество шпионов для комнаты:",
        reply_markup=build_spy_count_keyboard(room_id),
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
    inline_keyboard = get_inline_keyboard('join_game')
    keyboard = get_room_keyboard()
    spy_count = room.get("spy_count", 1)
    await update.message.reply_text(
        text = f"✅ Вы присоединились к комнате {room_id}!\n\n",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )
    await update.message.reply_text(
        text = get_join_room_text(room_id,len(players),get_theme_name(DEFAULT_MODE), spy_count=spy_count),
        parse_mode=ParseMode.HTML,
        reply_markup=inline_keyboard,
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
async def start_game(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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

    requested_spy_count = room.get("spy_count", 1) or 1
    if not isinstance(requested_spy_count, int):
        requested_spy_count = 1
    max_spies = max(1, len(players) - 1)
    spy_count = min(max(1, requested_spy_count), max_spies)
    if spy_count != requested_spy_count:
        await update.message.reply_text(
            f"ℹ️ Кол-во шпионов скорректировано до {spy_count} (игроков: {len(players)})."
        )
        await db.update_room_spy_count(room_id, spy_count)

    spies = set(random.sample(players, k=spy_count))
    primary_spy = next(iter(spies))

    await db.update_room_game_state(room_id, word, primary_spy, card_url)

    spies_label = "шпион" if spy_count == 1 else "шпионы"

    for player_id in players:
        if player_id in spies:
            await db.update_player_role(player_id, room_id, "шпион")

            account = await db.get_user_account(player_id)
            if not account:
                easy = medium = hard = 0
            else:
                easy = account["easy_hints"]
                medium = account["medium_hints"]
                hard = account["hard_hints"]
            keyboard_inline = get_game_inline_button(easy, medium, hard)

            cached_file_id = await db.get_cached_image(SPY_CARD_CACHE_KEY)

            try:
                if cached_file_id:
                    await context.bot.send_photo(
                        chat_id=player_id,
                        photo=cached_file_id,
                        caption=f"🎭 Вы - ШПИОН!\n\n❌ Вы не знаете слово!\n🎯 Ваша задача - понять слово.\n👥 Игроков: {len(players)}\n\n💡 Подсказка: это объект из {get_theme_name(mode)}",
                        reply_markup=keyboard_inline,
                    )

                elif SPY_CARD_BYTES:
                    result = await context.bot.send_photo(
                        chat_id=player_id,
                        photo=InputFile(
                            BytesIO(SPY_CARD_BYTES), filename=SPY_CARD_PATH.name
                        ),
                        caption=f"🎭 Вы - ШПИОН!\n\n❌ Вы не знаете слово!\n🎯 Ваша задача - понять слово.\n👥 Игроков: {len(players)}\n\n💡 Подсказка: это объект из {get_theme_name(mode)}",
                        reply_markup=keyboard_inline,
                    )

                    if hasattr(result, "photo") and result.photo:
                        await db.cache_image(
                            SPY_CARD_CACHE_KEY,
                            result.photo[-1].file_id,
                            mode,
                        )
                else:
                    await context.bot.send_photo(
                        chat_id=player_id,
                        photo=SINGLE_MODE_SPY_IMAGE_URL,
                        caption=f"🎭 Вы - ШПИОН!\n\n❌ Вы не знаете слово!\n🎯 Ваша задача - понять слово.\n👥 Игроков: {len(players)}\n\n💡 Подсказка: это объект из {get_theme_name(mode)}",
                        reply_markup=keyboard_inline,
                    )

            except Exception as e:
                logger.error(f"Error sending spy photo: {e}")

                await context.bot.send_message(
                    player_id,
                    f"🎭 Вы - ШПИОН!\n\n❌ Вы не знаете слово!\n🎯 Ваша задача - понять слово.\n👥 Игроков: {len(players)}",
                    reply_markup=keyboard_inline,
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
                            caption=f"✅ Вы - мирный игрок!\n\n🎴 Загаданная карта: <b>{word}</b>\n👥 Игроков: {len(players)}\n⚠️ Среди вас есть {spies_label}!",
                            parse_mode=ParseMode.HTML,
                        )

                    else:
                        result = await context.bot.send_photo(
                            chat_id=player_id,
                            photo=card_url,
                            caption=f"✅ Вы - мирный игрок!\n\n🎴 Загаданная карта: <b>{word}</b>\n👥 Игроков: {len(players)}\n⚠️ Среди вас есть {spies_label}!",
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
                        f"✅ Вы - мирный игрок!\n\n🎴 Загаданная карта: <b>{word}</b>\n👥 Игроков: {len(players)}\n⚠️ Среди вас есть {spies_label}!",
                        parse_mode=ParseMode.HTML,
                    )

            else:
                await context.bot.send_message(
                    player_id,
                    f"✅ Вы - мирный игрок!\n\n🎴 Загаданная карта: <b>{word}</b>\n👥 Игроков: {len(players)}\n⚠️ Среди вас есть {spies_label}!",
                    parse_mode=ParseMode.HTML,
                )

    for player_id in players:
        try:
            await context.bot.send_message(
                player_id,
                f"🎮 Игра началась!\n👥 Игроков: {len(players)}\n🕵️ Шпионов: {spy_count}\n🎴 Тема: {get_theme_name(mode)}\n\n💬 Можно начинать обсуждение!",
            )

        except:
            pass


@subscription_required
@decorators.rate_limit()
@decorators.creator_only()
@decorators.game_not_started()
@decorators.room_lock()
async def set_spies(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    room_id = await db.get_user_room(user_id)
    if not room_id:
        await update.message.reply_text("❌ Вы не в комнате!")
        return

    room = await db.get_room(room_id)
    if not room:
        await update.message.reply_text("❌ Комната не найдена!")
        return

    players = await db.get_room_players(room_id)
    current = room.get("spy_count", 1) or 1
    max_spies = max(1, len(players) - 1)

    if not context.args:
        await update.message.reply_text(
            f"🕵️ Сейчас шпионов: {current}\n"
            f"🕹️ Игроков: {len(players)}\n"
            f"✅ Установить: /spies <число>\n"
            f"ℹ️ Допустимо сейчас: 1–{max_spies}"
        )
        return

    try:
        requested = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Использование: /spies <число>")
        return

    if requested < 1:
        requested = 1
    if requested > max_spies:
        requested = max_spies

    await db.update_room_spy_count(room_id, requested)
    await update.message.reply_text(
        f"✅ Кол-во шпионов установлено: {requested}\n"
        f"ℹ️ Для смены позже: /spies <число>"
    )


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

    inline_keyboard = get_inline_keyboard('restart_game')

    await update.message.reply_text(
        get_restart_room_text(room_id,players,room),
        parse_mode=ParseMode.HTML,
        reply_markup=inline_keyboard,
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
            cached_file_id = await db.get_cached_image(SPY_CARD_CACHE_KEY)

            if cached_file_id:
                await context.bot.send_photo(
                    chat_id=user_id,
                    photo=cached_file_id,
                    caption=f"🎭 Вы - ШПИОН!\n\n❌ Вы не знаете слово!\n👥 Игроков: {len(await db.get_room_players(room_id))}",
                )

            elif SPY_CARD_BYTES:
                result = await context.bot.send_photo(
                    chat_id=user_id,
                    photo=InputFile(BytesIO(SPY_CARD_BYTES), filename=SPY_CARD_PATH.name),
                    caption=f"🎭 Вы - ШПИОН!\n\n❌ Вы не знаете слово!\n👥 Игроков: {len(await db.get_room_players(room_id))}",
                )
                if hasattr(result, "photo") and result.photo:
                    room = await db.get_room(room_id)
                    mode = (room or {}).get("mode", DEFAULT_MODE)
                    await db.cache_image(
                        SPY_CARD_CACHE_KEY,
                        result.photo[-1].file_id,
                        mode,
                    )
            else:
                await context.bot.send_photo(
                    chat_id=user_id,
                    photo=SINGLE_MODE_SPY_IMAGE_URL,
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
async def room_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    room_id = await db.get_user_room(user_id)
    if not room_id:
        await update.message.reply_text(
            "❌ Вы не в комнате.\n"
            "Создать: /create\n"
            "Войти: /join <ID>"
        )
        return
    room = await db.get_room(room_id)
    players = await db.get_room_players(room_id)
    spy_count = (room or {}).get("spy_count", 1)
    started = (room or {}).get("game_started", False)
    await update.message.reply_text(
        f"🏠 Комната: {room_id}\n"
        f"👥 Игроков: {len(players)}\n"
        f"🕵️ Шпионов: {spy_count}\n"
        f"🎮 Игра: {'идёт' if started else 'не начата'}\n\n"
        "💬 Чтобы писать в чат комнаты — просто отправляйте обычные сообщения сюда."
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


async def _validate_room_for_mode_change(update: Update):
    user_id = update.effective_user.id

    room_id = await db.get_user_room(user_id)
    if not room_id:
        await update.message.reply_text("❌ Вы не в комнате!")
        return None

    room = await db.get_room(room_id)
    if not room:
        await update.message.reply_text("❌ Комната не найдена!")
        return None

    if room["creator_id"] != user_id:
        await update.message.reply_text(
            "⛔ Эта команда только для создателя комнаты!"
        )
        return None

    if room.get("game_started"):
        await update.message.reply_text("❌ Нельзя менять режим во время игры!")
        return None

    return room_id, room


async def _announce_mode_change(update: Update, mode: str):
    words, _ = get_words_and_cards_by_mode(mode)
    entity_label = MODE_ENTITY_LABELS.get(mode, "вариантов")
    await update.message.reply_text(
        (
            f"✅ Режим изменён на {get_theme_name(mode)}.\n"
            "▶️ Начать игру и 🔄 Перезапустить уже доступны ниже."
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=get_room_keyboard(),
    )


async def _update_room_mode(update: Update, mode: str):
    room_info = await _validate_room_for_mode_change(update)
    if not room_info:
        return
    room_id, room = room_info
    if room["mode"] == mode:
        await update.message.reply_text(
            f"ℹ️ Режим уже {get_theme_name(mode)}.",
            reply_markup=get_room_keyboard(),
        )
        return

    await db.update_room_mode(room_id, mode)
    await _announce_mode_change(update, mode)


@subscription_required
@decorators.rate_limit()
@decorators.private_chat_only()
@decorators.creator_only()
@decorators.room_lock()
async def set_mode_clash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _update_room_mode(update, MODE_CLASH)


@subscription_required
@decorators.rate_limit()
@decorators.private_chat_only()
@decorators.creator_only()
@decorators.room_lock()
async def set_mode_dota(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _update_room_mode(update, MODE_DOTA)


@subscription_required
@decorators.rate_limit()
@decorators.private_chat_only()
@decorators.creator_only()
@decorators.room_lock()
async def set_mode_brawl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _update_room_mode(update, MODE_BRAWL)


@subscription_required
@decorators.rate_limit()
async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN:
        await update.message.reply_text("❌ Команда доступна только админам.")
        return
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

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN:
        await update.message.reply_text("❌ Нет доступа.")
        return
    await update.message.reply_text(
        "<b>🔧 Админ панель</b>\n\nВыберите действие:",
        reply_markup=get_admin_panel_keyboard(),
        parse_mode=ParseMode.HTML,
    )


async def admin_single_mode_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN:
        await update.message.reply_text("❌ Нет доступа.")
        return
    parts = [
        f"⏱️ Сеансов single мода сейчас: {len(SINGLE_MODE_SESSIONS)}",
        "",
    ]
    for session_user_id, sess in SINGLE_MODE_SESSIONS.items():
        time_str = sess.time.strftime("%H:%M:%S %Y-%m-%d")
        parts.append(
            f"{session_user_id} | {sess.word} | {sess.player_count} | {time_str}"
        )
    await context.bot.send_message(
        chat_id=user_id,
        text="\n".join(parts),
        parse_mode=ParseMode.HTML,
    )


async def admin_global_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN:
        await update.message.reply_text("❌ Нет доступа.")
        return
    stats = await db.get_all_rooms_stats()
    await update.message.reply_text(
        f"📊 Общая статистика бота:\n\n"
        f"🏠 Всего комнат: {stats['total_rooms']}\n"
        f"🎮 Активных игр: {stats['active_rooms']}\n"
        f"👤 Всего игроков: {stats['total_players']}"
    )


async def admin_broadcast_subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN:
        await update.message.reply_text("❌ Нет доступа.")
        return

    status_msg = await update.message.reply_text("⏳ Запускаю рассылку...")
    user_ids = await db.get_all_known_user_ids()

    text = (
        "<b>📢 SpionGame — наш канал</b>\n\n"
        "Тут выходят обновы бота и анонсы.\n"
        "Также иногда можно поиграть вместе с админами.\n\n"
        "Нажми кнопку ниже и подпишись, чтобы не пропускать 🔥"
    )
    sent = 0
    failed = 0
    for idx, recipient_id in enumerate(user_ids, start=1):
        try:
            await context.bot.send_message(
                chat_id=recipient_id,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=subscribe_keyboard(),
            )
            sent += 1
        except Exception:
            failed += 1
        if idx % 25 == 0:
            await asyncio.sleep(0.2)

    await status_msg.edit_text(
        f"✅ Рассылка завершена.\nОтправлено: {sent}\nОшибок: {failed}"
    )


async def single_mode_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    user_id = query.from_user.id
    parts = query.data.split(":")
    if len(parts) < 2:
        return
    action = parts[1]

    if action == "select":
        if len(parts) != 3:
            return
        try:
            player_count = int(parts[2])
        except ValueError:
            return
        if player_count not in SINGLE_MODE_PLAYER_OPTIONS:
            await query.answer("Выберите доступное число игроков.", show_alert=True)
            return
        context.user_data["single_pending_players"] = player_count
        await query.answer()
        keyboard = _build_single_mode_spy_selection_keyboard(
            player_count, callback_prefix="single:setup_spies:", include_back=False
        )
        try:
            await query.message.edit_text(
                "🕵️ Выберите количество шпионов", reply_markup=keyboard
            )
        except BadRequest:
            pass
        return

    if action == "setup_spies":
        if len(parts) != 3:
            return
        pending_players = context.user_data.get("single_pending_players")
        if not isinstance(pending_players, int):
            await query.answer("Сначала выберите игроков.", show_alert=True)
            return
        try:
            spy_count = int(parts[2])
        except ValueError:
            return
        await query.answer()
        session = _create_single_mode_session(
            pending_players, DEFAULT_MODE, spy_count=spy_count
        )
        if not session:
            await query.answer("К сожалению, нет доступных карт.", show_alert=True)
            return
        context.user_data.pop("single_pending_players", None)
        session.chat_id = user_id
        message = await _send_single_mode_card(user_id, context, session)
        session.message_id = message.message_id
        SINGLE_MODE_SESSIONS[user_id] = session
        try:
            await query.message.delete()
        except BadRequest:
            pass
        return

    if action == "cancel":
        await query.answer()
        context.user_data.pop("single_pending_players", None)
        try:
            await query.message.edit_text("❌ Сессия отменена.")
        except BadRequest:
            pass
        return

    session = SINGLE_MODE_SESSIONS.get(user_id)
    if not session:
        await query.answer("Сессия завершена. Запустите режим снова.", show_alert=True)
        return
    await query.answer()

    total = session.player_count
    if total == 0:
        await query.answer("Сессия инициализирована неправильно.", show_alert=True)
        return

    if action == "prev":
        session.current_index = (session.current_index - 1) % total
        session.revealed = False
        await _update_single_mode_message(query, session)
    elif action == "next":
        session.current_index = (session.current_index + 1) % total
        session.revealed = False
        await _update_single_mode_message(query, session)
    elif action == "reveal":
        session.revealed = not session.revealed
        await _update_single_mode_message(query, session)
    elif action == "spy_menu":
        keyboard = _build_single_mode_spy_selection_keyboard(
            session.player_count, callback_prefix="single:set_spies:", include_back=True
        )
        try:
            await query.message.edit_caption(
                caption="🕵️ Выберите количество шпионов",
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
            )
        except BadRequest:
            pass
    elif action == "set_spies":
        if len(parts) != 3:
            return
        try:
            spy_count = int(parts[2])
        except ValueError:
            return
        new_session = _create_single_mode_session(
            session.player_count, session.mode, spy_count=spy_count
        )
        if new_session:
            new_session.chat_id = session.chat_id
            new_session.message_id = session.message_id
            new_session.back_card_file_id = session.back_card_file_id
            new_session.spy_card_file_id = session.spy_card_file_id
            SINGLE_MODE_SESSIONS[user_id] = new_session
            await context.bot.send_message(
                chat_id=user_id,
                text=f"✅ Кол-во шпионов: {new_session.spy_count}. Сессия обновлена.",
            )
            await _update_single_mode_message(query, new_session)
    elif action == "back":
        await _update_single_mode_message(query, session)
    elif action == "restart":
        new_session = _create_single_mode_session(
            session.player_count, session.mode, spy_count=session.spy_count
        )
        if new_session:
            new_session.chat_id = session.chat_id
            new_session.message_id = session.message_id
            new_session.back_card_file_id = session.back_card_file_id
            new_session.spy_card_file_id = session.spy_card_file_id
            SINGLE_MODE_SESSIONS[user_id] = new_session
            await context.bot.send_message(
                chat_id=user_id,
                text="🔁 Single мод перезапущен! Сделайте новое раскрытие карты.",
            )
            await _update_single_mode_message(query, new_session)
    elif action == "exit":
        SINGLE_MODE_SESSIONS.pop(user_id, None)
        try:
            await query.message.delete()
        except BadRequest:
            pass
        await show_main_menu(user_id, context)
    # noop or unknown actions require no response


@decorators.rate_limit(max_requests=5, period=1.0)
async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if context.user_data.get("awaiting_custom_donate_amount"):
        amount_text = text.strip()
        if amount_text.isdigit():
            amount = int(amount_text)
            if amount <= 0:
                await update.message.reply_text("Сумма должна быть больше нуля.")
                return
            context.user_data.pop("awaiting_custom_donate_amount", None)
            await _send_donate_invoice(update.effective_chat.id, context, amount)
        else:
            await update.message.reply_text("Введите сумму числом.")
        return
    # user_id = update.effective_user.id не используется в функции

    if text == "🎮 Создать комнату":
        await create_room(update, context)
    elif text == "🔗 Присоединиться":
        await join_room(update, context)
    elif text in MODE_SELECTION_LABELS:
        await _update_room_mode(update, MODE_SELECTION_LABELS[text])
    elif text == "▶️ Начать игру":
        await start_game(update, context)
    elif text == "🔄 Перезапустить":
        await restart_game(update, context)
    elif text == "📖 Правила":
        await rules(update, context)
    elif text == "🃏 Сингл мод":
        await single_mode(update, context)
    elif text == "🎴 Все карты":
        await show_cards(update, context)
    elif text == "👤 Моя роль/слово":
        await get_word(update, context)
    elif text == "👥 Игроки в комнате":
        await show_players(update, context)
    elif text == "🚪 Выйти из комнаты":
        await leave_room(update, context)
    elif text == "👤 Личный кабинет":
        await personal_account(update, context)
    elif text == "🎁 Реферальная система":
        await referral_system(update, context)
    elif text == "ℹ️ Помощь" or text == "🏠 Главное меню":
        user_id = update.effective_user.id
        room_id = await db.get_user_room(user_id)

        if room_id:
            await leave_room(update, context)

        await start(update, context)
    elif text == "😈 Админ Панель":
        await admin_panel(update, context)
    elif text == "📊 Стата сингл мода":
        await admin_single_mode_stats(update, context)
    elif text == "📈 Общая стата":
        await admin_global_stats(update, context)
    elif text == "📢 Запустить рассылку":
        await admin_broadcast_subscribe(update, context)
    elif text == "⬅️ Назад":
        user_id = update.effective_user.id
        if user_id in ADMIN:
            await show_main_menu(user_id, context)
        else:
            await update.message.reply_text("Используйте кнопки меню или команды.")
    elif text.isdigit() and len(text) == 4:
        context.args = [text]
        await join_room(update, context)
    else:
        user_id = update.effective_user.id
        room_id = await db.get_user_room(user_id)
        if room_id:
            await _broadcast_room_chat(
                room_id=room_id,
                sender_id=user_id,
                sender_user=update.effective_user,
                text=text,
                context=context,
            )
        else:
            await update.message.reply_text(
                "❌ Вы не в комнате.\n"
                "Создать: /create\n"
                "Войти: /join <ID>\n"
                "Проверить комнату: /room"
            )


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
    prices = [LabeledPrice(label="Поддержка автора", amount=1)]
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


async def successful_payment_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """
    После успешной оплаты можно поблагодарить пользователя
    """
    payment = update.message.successful_payment
    user_id = update.effective_user.id
    stars = payment.total_amount
    new_balance = await db.add_balance(user_id, stars)
    balance_text = f"{new_balance}⭐" if new_balance is not None else "?"
    await update.message.reply_text(
        f"Спасибо за поддержку! Вы пожертвовали {stars}⭐.\n"
        f"💳 Баланс: {balance_text}"
    )


def _format_price_list():
    ordered = ["easy", "medium", "hard"]
    return "\n".join(
        f"• {HINT_LABELS[item]}: {HINT_PRICES[item]} ⭐" for item in ordered
    )

def _build_quantity_keyboard(hint_type: str):
    buttons = []
    for qty in HINT_QUANTITIES:
        total = qty * HINT_PRICES[hint_type]
        buttons.append(
            InlineKeyboardButton(
                f"{qty} шт. — {total} ⭐",
                callback_data=f"buy_confirm:{hint_type}:{qty}",
            )
        )
    buttons.append(
        InlineKeyboardButton("⬅️ Назад", callback_data="buy_type:back")
    )
    rows = [buttons[i : i + 3] for i in range(0, len(buttons), 3)]
    return InlineKeyboardMarkup(rows)


async def _process_hint_purchase(user_id: int, hint_type: str, quantity: int):
    price_per_hint = HINT_PRICES[hint_type]
    total_cost = price_per_hint * quantity
    result = await db.purchase_hints(
        user_id,
        total_cost,
        hard=quantity if hint_type == "hard" else 0,
        medium=quantity if hint_type == "medium" else 0,
        easy=quantity if hint_type == "easy" else 0,
    )

    if not result:
        account = await db.get_user_account(user_id) or {"balance": 0}
        message = (
            f"❌ Недостаточно звезд на балансе ({account.get('balance', 0)}⭐) — "
            f"нужно {total_cost}⭐. Пополните через /donate и попробуйте снова."
        )
        return False, message

    message = (
        f"✅ Вы купили {quantity} {HINT_LABELS[hint_type]} подсказок за {total_cost}⭐.\n"
        f"⭐ Баланс: {result['balance']}⭐\n"
        "📦 Сейчас на счету:\n"
        f"• {HINT_LABELS['hard']}: {result['hard_hints']} шт.\n"
        f"• {HINT_LABELS['medium']}: {result['medium_hints']} шт.\n"
        f"• {HINT_LABELS['easy']}: {result['easy_hints']} шт."
    )
    return True, message

async def _send_donate_invoice(
    chat_id: int, context: ContextTypes.DEFAULT_TYPE, amount: int
):
    prices = [LabeledPrice(label=f"{amount} ⭐", amount=amount * 1)]
    await context.bot.send_invoice(
        chat_id=chat_id,
        title="Пополнение баланса",
        description=f"Вы пополняете баланс на {amount} ⭐",
        payload=f"donate_{amount}",
        currency="XTR",
        prices=prices,
        start_parameter="donate",
        provider_token="",
    )


async def _get_account_summary(user_id: int):
    await db.ensure_user_account(user_id)
    account = await db.get_user_account(user_id) or {}
    return (
        account.get("balance", 0) or 0,
        account.get("hard_hints", 0) or 0,
        account.get("medium_hints", 0) or 0,
        account.get("easy_hints", 0) or 0,
    )


@subscription_required
@decorators.rate_limit()
@decorators.private_chat_only()
async def referral_system(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    bot_username = context.bot.username or ""
    referral_code = f"ref{user_id}"
    referral_link = (
        f"https://t.me/{bot_username}?start={referral_code}" if bot_username else None
    )
    total_referrals = await db.get_referral_count(user_id)
    earned_stars = total_referrals * 2
    lines = [
        "<b>🎁 Реферальная система</b>",
        "",
        "🎯 Поделитесь ссылкой и получайте бонусы.",
        "Каждый приглашённый приносит вам 2⭐, а ему достаётся 1⭐.",
    ]
    if referral_link:
        lines.append(
            f"🔗 Ваша ссылка: <a href=\"{referral_link}\">{referral_link}</a>"
        )
    lines.extend(
        [
            f"🆔 Код: <code>{referral_code}</code>",
            f"👥 Приглашено друзей: {total_referrals}",
            f"💰 Вы заработали: {earned_stars}⭐",
        ]
    )
    keyboard = []
    if referral_link:
        keyboard.append(
            [InlineKeyboardButton("🔗 Поделиться ссылкой", url=referral_link)]
        )
    keyboard.append(
        [InlineKeyboardButton("🏠 Главное меню", callback_data="cabinet:menu")]
    )
    await update.message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


@subscription_required
@decorators.rate_limit()
@decorators.private_chat_only()
async def personal_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    balance, hard_count, medium_count, easy_count = await _get_account_summary(
        user_id
    )

    await update.message.reply_text(
        _personal_account_text(
            update.effective_user,
            balance,
            hard_count,
            medium_count,
            easy_count,
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=_build_cabinet_keyboard(),
    )


@subscription_required
@decorators.rate_limit()
@decorators.private_chat_only()
async def buy_hint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args or []
    if len(args) >= 2:
        hint_type = args[0].lower()
        if hint_type not in HINT_PRICES:
            await update.message.reply_text(
                f"Неизвестный тип подсказки: {hint_type}. "
                f"Доступны: {', '.join(HINT_PRICES.keys())}"
            )
            return

        try:
            quantity = int(args[1])
        except ValueError:
            await update.message.reply_text("Количество должно быть числом.")
            return

        if quantity <= 0:
            await update.message.reply_text("Количество должно быть больше нуля.")
            return

        _, message = await _process_hint_purchase(user_id, hint_type, quantity)
        await update.message.reply_text(message)
        return

    price_text = (
        "🛒 Купить подсказки:\n"
        f"{_format_price_list()}\n\n"
        "Выберите тип подсказки, чтобы продолжить."
    )
    await update.message.reply_text(
        price_text, reply_markup=_build_hint_selection_keyboard()
    )


async def buy_hint_type_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    parts = query.data.split(":", 1)
    if len(parts) != 2:
        return
    hint_type = parts[1]
    if hint_type == "back":
        price_text = (
            "🛒 Купить подсказки:\n"
            f"{_format_price_list()}\n\n"
            "Выберите тип подсказки, чтобы продолжить."
        )
        await query.message.edit_text(
            price_text, reply_markup=_build_hint_selection_keyboard()
        )
        return

    if hint_type not in HINT_PRICES:
        await query.message.edit_text(
            "Неизвестный тип подсказки.", reply_markup=_build_hint_selection_keyboard()
        )
        return

    text = (
        f"💠 Вы выбрали {HINT_LABELS[hint_type]}.\n"
        f"Цена за штуку: {HINT_PRICES[hint_type]}⭐\n\n"
        "Выберите количество:"
    )
    await query.message.edit_text(
        text, reply_markup=_build_quantity_keyboard(hint_type)
    )


async def buy_hint_confirm_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    parts = query.data.split(":")
    if len(parts) != 3:
        return
    _, hint_type, qty_str = parts
    if hint_type not in HINT_PRICES:
        await query.message.edit_text(
            "Неизвестный тип подсказки.", reply_markup=_build_hint_selection_keyboard()
        )
        return

    try:
        quantity = int(qty_str)
    except ValueError:
        await query.message.edit_text(
            "Неправильное количество.", reply_markup=_build_hint_selection_keyboard()
        )
        return

    success, message = await _process_hint_purchase(
        query.from_user.id, hint_type, quantity
    )
    suffix = (
        "\n\n🛒 Хотите ещё? Выберите тип ниже."
        if success
        else "\n\nПопробуйте другой тип или пополните баланс через /donate."
    )
    await query.message.edit_text(
        message + suffix, reply_markup=_build_hint_selection_keyboard()
    )


async def buy_hint_cancel_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    await query.message.edit_text("❌ Покупка отменена.")


async def cabinet_action_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    action = query.data.split(":", 1)[-1]

    if action == "menu":
        await query.message.delete()
        await show_main_menu(query.from_user.id, context)
        return

    if action == "buy_hints":
        price_text = (
            "🛒 Купить подсказки:\n"
            f"{_format_price_list()}\n\n"
            "Выберите тип подсказки, чтобы продолжить."
        )
        await query.message.edit_text(
            price_text, reply_markup=_build_hint_selection_keyboard()
        )
        return

    if action == "donate":
        await query.message.edit_text(
            "💳 Выберите, сколько звезд хотите пополнить:", reply_markup=_build_donate_keyboard()
        )
        return

    if action == "account":
        balance, hard, medium, easy = await _get_account_summary(query.from_user.id)
        await query.message.edit_text(
            _personal_account_text(
                query.from_user, balance, hard, medium, easy
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=_build_cabinet_keyboard(),
        )


async def donate_amount_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    parts = query.data.split(":")
    if len(parts) != 2:
        return
    _, amount_str = parts
    amount_str = amount_str.strip()
    if not amount_str.isdigit():
        context.user_data["awaiting_custom_donate_amount"] = True
        await query.message.edit_text(
            "Введите свою сумму пополнения числом.",
            reply_markup=_build_cabinet_keyboard(),
        )
        return
    context.user_data.pop("awaiting_custom_donate_amount", None)
    try:
        amount = int(amount_str)
    except ValueError:
        await query.message.edit_text(
            "Неправильная сумма. Выберите снова.",
            reply_markup=_build_donate_keyboard(),
        )
        return

    await _send_donate_invoice(query.message.chat_id, context, amount)
    await query.message.edit_text(
        f"🧾 Формирую счёт на {amount} ⭐. Проверьте чат.",
        reply_markup=_build_cabinet_keyboard(),
    )
