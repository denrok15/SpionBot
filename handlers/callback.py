from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from const import (
    MODE_CLASH,
)
from database.actions import db
from handlers.button import get_room_keyboard
from utils.gameMod import get_theme_name, get_words_and_cards_by_mode

DEFAULT_MODE = MODE_CLASH
async def show_clues_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    await query.message.edit_text(
        "💡 Подсказки:\n\n"
        "Подсказки помогут тебе понять быстрее что за персонаж загадан!\n"
        "Существует 3 вида подсказок:\n"
        "1)Hard - абстрактный факт,который максимально обще будет описать персонажа(Цена: 5✨)\n"
        "2)Meduim - факты,который поймет любитель и профессионалы,но не многие новички(Цена: 10✨)\n"
        "3)Easy - факт,который будет понятен даже новичкам!(Цена: 20✨)\n"
        "Ниже ты можешь заранее выбрать подсказка,какая будет в игре. Если-же у вас нет подсказок,то их можно приобрести в личном кабинете в главном меню.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_room"),
             InlineKeyboardButton("🔴 Хард", callback_data="ЕЕЕЕЕЕЕЕЕЕЕ"),
             InlineKeyboardButton("🟡 Медиум", callback_data="ЕЕЕЕЕЕЕЕЕЕЕ"),
             InlineKeyboardButton("🟢 Лёгкая", callback_data="ЕЕЕЕЕЕЕЕЕЕЕ")]
        ])
    )
async def back_to_room_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    message = query.message

    room_id = await db.get_user_room(user_id)
    if not room_id:
        await message.reply_text("Ты пока не в комнате. Создай новую /create")
        return

    room = await db.get_room(room_id)
    if not room:
        await message.reply_text("Комната не найдена, попробуй создать новую /create")
        return

    mode = room.get("mode", DEFAULT_MODE)
    words, _ = get_words_and_cards_by_mode(mode)

    keyboard = get_room_keyboard()
    inline_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(text="🧩 Подсказки", callback_data="check_clue")]
    ])

    await message.reply_text("\u200b", reply_markup=keyboard)
    await message.reply_text(
        f"Комната создана!\n\nID комнаты: <code>{room_id}</code>\n"
        f"Сложность: 1/15\n"
        f"Тема: {get_theme_name(mode)}\n"
        f"Слова в пуле: {len(words)}\n"
        f"Сменить тему: /mode_clash или /mode_dota\n\n"
        f"Когда все готовы, жми /startgame",
        parse_mode=ParseMode.HTML,
        reply_markup=inline_keyboard,
    )
