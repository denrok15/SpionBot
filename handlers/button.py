from telegram import ReplyKeyboardMarkup,InlineKeyboardMarkup,InlineKeyboardButton
from utils.gameMod import get_theme_name
from const import HINT_TEXT,HINT_LABELS, HINT_PRICES,DONATE_AMOUNTS

def get_main_keyboard(admin : str | None = None) -> ReplyKeyboardMarkup:
    keyboard = [
            ["🎮 Создать комнату", "🔗 Присоединиться"],
            ["👤 Личный кабинет", "📖 Правила"],
            ["🃏 Сингл мод", "🎁 Реферальная система"],
        ]
    if admin is not None:
        keyboard.append([admin])
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
    )

def get_admin_panel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            ["📊 Стата сингл мода","📈 Общая стата"],
            ["📢 Запустить рассылку","⬅️ Назад"], 
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
def get_message_start(room_id: str, players: int, mode: str, spy_count: int = 1) -> str:
    return (
        f"ID комнаты: <code>{room_id}</code>\n"
        f"Отправьте этот ID другим игрокам\n\n"
        f"👥 Игроков: {str(players)}/15\n"
        f"🎴 Режим: {mode}\n"
        f"🕵️ Шпионов: {spy_count}\n"
        f"🕵️ Сменить: /spies &lt;число&gt;\n"
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
    f"🕵️ Шпионов: {room.get('spy_count', 1)}\n"
    f"🕵️ Сменить: /spies &lt;число&gt;\n"
    f"🎱 Используй для смены режимы \n /mode_clash /mode_dota /mode_brawl \n"
    f"Для начала новой игры нажмите '▶️ Начать игру'")

def get_join_room_text(room_id,players,mode, spy_count: int = 1) -> str:
    return (
        f"ID комнаты: <code>{room_id}</code>\n"
        f"Отправьте этот ID другим игрокам\n\n"
        f"👥 Игроков: {str(players)}/15\n"
        f"🎴 Режим: {mode}\n"
        f"🕵️ Шпионов: {spy_count}\n"
        f"🔥 Тыкни на подсказки и узнай как побеждать проще 🙂")


def build_spy_count_keyboard(room_id: str, max_spies: int = 7) -> InlineKeyboardMarkup:
    options = list(range(1, max_spies + 1))
    rows = []
    for i in range(0, len(options), 3):
        rows.append(
            [
                InlineKeyboardButton(
                    f"{count}", callback_data=f"spies:set:{room_id}:{count}"
                )
                for count in options[i : i + 3]
            ]
        )
    return InlineKeyboardMarkup(rows)
def _build_cabinet_keyboard():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🏠 Главное меню", callback_data="cabinet:menu"),
                InlineKeyboardButton(
                    "🛒 Купить подсказки", callback_data="cabinet:buy_hints"
                ),
            ],
            [
                InlineKeyboardButton(
                    "💳 Пополнить баланс", callback_data="cabinet:donate"
                )
            ],
        ]
    )

def _build_hint_selection_keyboard():
    keyboard = [
        [
            InlineKeyboardButton(
                f"{HINT_LABELS[hint_type]} — {HINT_PRICES[hint_type]} ⭐",
                callback_data=f"buy_type:{hint_type}",
            )
        ]
        for hint_type in ["easy", "medium", "hard"]
    ]
    keyboard.append(
        [InlineKeyboardButton("⬅️ Назад", callback_data="cabinet:account")]
    )
    return InlineKeyboardMarkup(keyboard)
def _personal_account_text(user, balance, hard, medium, easy):
    name = user.full_name or user.username or "Игрок"
    return (
        "<b>👤 Личный кабинет</b>\n\n"
        f"🔸 Имя: <b>{name}</b>\n\n"
        "📊 Статистика шпиона:\n"
        f"⭐ Баланс: <b>{balance}</b> ⭐\n\n"
        "📦 На счету подсказок:\n"
        f"• {HINT_LABELS['hard']}: {hard} шт.\n"
        f"• {HINT_LABELS['medium']}: {medium} шт.\n"
        f"• {HINT_LABELS['easy']}: {easy} шт.\n\n"
        "💳 Чтобы пополнить баланс, используйте /donate или меню ниже\n"
        "🛒 Чтобы купить подсказки, воспользуйтесь меню ниже."
)


def _build_donate_keyboard():
    buttons = [
        InlineKeyboardButton(
            f"{amount} ⭐", callback_data=f"donate_amount:{amount}"
        )
        for amount in DONATE_AMOUNTS
    ]
    buttons.append(
        InlineKeyboardButton("⬅️ Назад", callback_data="cabinet:account")
    )
    rows = [buttons[i : i + 3] for i in range(0, len(buttons), 3)]
    return InlineKeyboardMarkup(rows)
