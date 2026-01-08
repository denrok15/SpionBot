from telegram import ReplyKeyboardMarkup


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


def get_room_mode_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [["🎲 Дота 2", "🃏 Clash Royale", "🎮 Brawl Stars"],
         ["🚪 Выйти из комнаты", "🏠 Главное меню"],
         ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )
