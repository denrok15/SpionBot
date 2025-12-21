import random
from typing import Literal


class UserClue:
    def __init__(self):
        self.clue_dota2 = {}
        self.clue_clash_royale = {}
        self.clues = {
            "dota2": self.clue_dota2,
            "clash_royale": self.clue_clash_royale,
        }

    def found_clue(
        self,
        game: Literal["dota2", "clash_royale"],
        hero: str,  # название героев нужно брать строго из CONST.PY
        complexity: Literal["easy", "medium", "hard"],
    ):
        number = random.randint(0, 5)
        return self.clues[game][hero][complexity][number]
clue_obj = UserClue()
