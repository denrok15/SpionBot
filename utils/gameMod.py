from const import (
    CARDS_BRAWL,
    CARDS_CLASH,
    MODE_BRAWL,
    MODE_CLASH,
    MODE_DOTA,
    WORDS_BRAWL,
    WORDS_CLASH,
    dotaImages,
    namesDota,
)

DEFAULT_MODE = MODE_CLASH


def get_words_and_cards_by_mode(mode: str):
    if mode == MODE_DOTA:
        return namesDota, dotaImages
    if mode == MODE_BRAWL:
        return WORDS_BRAWL, CARDS_BRAWL
    return WORDS_CLASH, CARDS_CLASH


def get_theme_name(mode: str) -> str:
    if mode == MODE_DOTA:
        return "Герои Dota 2"
    if mode == MODE_BRAWL:
        return "Бойцы Brawl Stars"
    return "Карты Clash Royale"
