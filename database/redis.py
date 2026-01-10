import redis
from dotenv import load_dotenv
from typing import Literal
import os
import random
import json
load_dotenv()
HOST = os.getenv("HOST")
PORT = os.getenv("PORT")
r = redis.Redis(
    host=HOST,
    port=PORT,
    db=0,
    decode_responses=True
)
def set_clue_hero(hero : str,content : dict)->None:
    r.set(hero, json.dumps(content))
def get_clue_hero(hero : str,complexity: Literal["easy", "medium", "hard"]) -> str:
    value = json.loads(r.get(hero))
    number = random.randint(0,9)
    clue = value[complexity][number]
    return clue

