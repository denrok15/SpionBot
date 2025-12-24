import random
from typing import Literal


class UserClue:
    def __init__(self):
        self.clue_dota2 = {}
        self.clue_clashroyale = {}
        self.clues = {
            "dota2": self.clue_dota2,
            "clashroyale": self.clue_clashroyale,
        }

    def found_clue(
        self,
        game: Literal["dota2", "clashroyale"],
        hero: str,  # название героев нужно брать строго из CONST.PY
        complexity: Literal["easy", "medium", "hard"],
    ):
        number = random.randint(0, 4)
        return self.clues[game][hero][complexity][number]


clue_obj = UserClue()
