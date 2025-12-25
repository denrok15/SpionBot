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

def get_inline_keyboard()->InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(text="💡Подсказки",callback_data="show_clues")]]
    )


def get_message_start(room_id:str,players:int,mode : str,count_word:int)->str:
    return(
        f"ID комнаты: <code>{room_id}</code>\n"
        f"Отправьте этот ID другим игрокам\n\n"
        f"👥 Игроков: {str(players)}/15\n"
        f"🎴 Режим: {mode}\n"
        f"Доступно слов: {str(count_word)}\n"
        f"Создатель комнаты может сменить режим командами /mode_clash и /mode_dota\n\n"
        f"Для начала игры нажмите '▶️ Начать игру'\n"
        f"По кнопке ниже вы можете ознакомиться с подсказками для игры🙂"
    )