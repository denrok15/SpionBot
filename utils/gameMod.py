from const import (
    dotaImages,
    namesDota,
    MODE_CLASH,
    MODE_DOTA,
    WORDS_CLASH,
    CARDS_CLASH,
)
DEFAULT_MODE = MODE_CLASH
def get_words_and_cards_by_mode(mode: str):
    if mode == MODE_DOTA:
        return namesDota, dotaImages
    return WORDS_CLASH, CARDS_CLASH
def get_theme_name(mode: str) -> str:
    if mode == MODE_DOTA:
        return "Герои Dota 2"
    return "Карты Clash Royale"