from telegram import ReplyKeyboardMarkup
def get_main_keyboard():
    return ReplyKeyboardMarkup(
        [
            ["🎮 Создать комнату", "🔗 Присоединиться"],
            ["📖 Правила"],
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