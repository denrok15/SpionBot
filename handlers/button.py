from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

HINT_TEXT = {'easy':"🟢 Лёгкая",
             'hard':"🔴 Хард",
             'medium':"🟡 Медиум"}



def get_main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            ["🎮 Создать комнату", "🔗 Присоединиться"],
            ["👤 Личный кабинет", "📖 Правила"],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def get_room_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            ["▶️ Начать игру", "🔄 Перезапустить"],
            ["🚪 Выйти из комнаты", "🏠 Главное меню"],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )
def get_game_inline_button(easy: int, medium: int, hard: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(f'{HINT_TEXT["hard"]} ({hard})',   callback_data="check_clue:hard"),
        InlineKeyboardButton(f'{HINT_TEXT["medium"]} ({medium})', callback_data="check_clue:medium"),
        InlineKeyboardButton(f'{HINT_TEXT["easy"]} ({easy})',   callback_data="check_clue:easy"),
    ]])
