from telegram import ReplyKeyboardMarkup,InlineKeyboardMarkup,InlineKeyboardButton
from utils.gameMod import get_theme_name
HINT_TEXT = {'easy':"🟢 Лёгкая",
             'hard':"🔴 Хард",
             'medium':"🟡 Медиум"}

def get_main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            ["🎮 Создать комнату", "🔗 Присоединиться"],
            ["👤 Личный кабинет", "📖 Правила"],
            ["🃏 Сингл мод", "🎁 Реферальная система"],
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
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    f"{HINT_TEXT['hard']} ({hard})", callback_data="check_clue:hard"
                ),
                InlineKeyboardButton(
                    f"{HINT_TEXT['medium']} ({medium})",
                    callback_data="check_clue:medium",
                ),
                InlineKeyboardButton(
                    f"{HINT_TEXT['easy']} ({easy})", callback_data="check_clue:easy"
                ),
            ]
        ]
    )


def get_inline_keyboard(place : str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(text="💡Подсказки", callback_data=f"show_clues:{place}")]]
    )
def get_room_mode_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [["🎲 Дота 2", "🃏 Clash Royale", "🎮 Brawl Stars"],
         ["🚪 Выйти из комнаты", "🏠 Главное меню"],
         ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )
def get_message_start(room_id: str, players: int, mode: str) -> str:
    return (
        f"ID комнаты: <code>{room_id}</code>\n"
        f"Отправьте этот ID другим игрокам\n\n"
        f"👥 Игроков: {str(players)}/15\n"
        f"🎴 Режим: {mode}\n"
        f"⬇️ Выберите режим через кнопки снизу\n"
        f"🔄 Для быстрой смены режима можно использовать команды\n"
        f"📲 /mode_clash, /mode_dota или /mode_brawl \n"
        f"🔥 Тыкни на подсказки и узнай как побеждать проще 🙂"
    )
def get_restart_room_text(room_id,players,room) -> str:
    return (
    f"🔄 Игра перезапущена!\n\n"
    f"ID комнаты: <code>{room_id}</code>\n"
    f"👥 Игроков: {len(players)}\n"
    f"🎴 Режим: {get_theme_name(room['mode'])}\n"
    f"🎱 Используй для смены режимы \n /mode_clash /mode_dota /mode_brawl \n"
    f"Для начала новой игры нажмите '▶️ Начать игру'")

def get_join_room_text(room_id,players,mode) -> str:
    return (
        f"ID комнаты: <code>{room_id}</code>\n"
        f"Отправьте этот ID другим игрокам\n\n"
        f"👥 Игроков: {str(players)}/15\n"
        f"🎴 Режим: {mode}\n"
        f"🔥 Тыкни на подсказки и узнай как побеждать проще 🙂")