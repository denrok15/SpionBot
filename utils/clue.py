import os
import random
from typing import Literal
from dotenv import load_dotenv
import requests
import logging
load_dotenv()
logger = logging.getLogger(__name__)
HASH = os.getenv("HASH")
URL = os.getenv("URL")
def take_clue_serves(game : str)->dict:
    logger.info(f"Getting clue serves for {game}")
    payload = {
        "password": HASH,
        "game": game
    }
    headers = {
        "accept": "application/json",
        "Content-Type": "application/json"
}
    response = requests.post(URL, json=payload, headers=headers)

    return response.json()

class UserClue:
    def __init__(self):
        self.clue_dota2 = {}
        self.clue_clash_royale = {}
        self.clue_brawl_stars = {}
        self.clues = {
            "dota2": self.clue_dota2,
            "clash_royale": self.clue_clash_royale,
            "brawl_stars": self.clue_brawl_stars
        }

    def found_clue(
        self,
        game: Literal["dota2", "clash_royale","brawl_stars"],
        hero: str,  # название героев нужно брать строго из CONST.PY
        complexity: Literal["easy", "medium", "hard"],
    ):
        number = random.randint(0, 9)
        return self.clues[game][hero][complexity][number]


clue_obj = UserClue()
