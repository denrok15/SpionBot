import random
import requests
from typing import Literal
import os
from dotenv import load_dotenv

load_dotenv()

HASH = os.getenv("HASH")
URL = os.getenv("URL")


def take_clue_serves(game: str) -> dict:
    payload = {"password": HASH, "game": game}
    headers = {"accept": "application/json", "Content-Type": "application/json"}
    response = requests.post(URL, json=payload, headers=headers)
    return response.json()


class UserClue:
    def __init__(self):
        self.clue_dota2 = {}
        self.clue_clashroyale = {}
        self.clue_brawlstars = {}
        self.clues = {
            "dota2": self.clue_dota2,
            "clashroyale": self.clue_clashroyale,
            "brawlstart": self.clue_brawlstars,
        }

    def found_clue(
        self,
        game: Literal["dota2", "clashroyale", "brawlstars"],
        hero: str,  # название героев нужно брать строго из CONST.PY
        complexity: Literal["easy", "medium", "hard"],
    ):
        number = random.randint(0, 9)
        return self.clues[game][hero][complexity][number]


clue_obj = UserClue()
