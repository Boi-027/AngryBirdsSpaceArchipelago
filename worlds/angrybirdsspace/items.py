from BaseClasses import Item, ItemClassification
from .data import EPISODES

GAME = "Angry Birds Space"
BASE_ID = 0xAB5000

# game bird id -> item name
BIRDS = {
    "RedBird": "Red Bird", "SmallBlueBird": "Blue Birds", "LaserBird": "Lazer Bird", "BlackBird": "Firebomb Bird",
    "IceBird": "Ice Bird", "RedBigBird": "Big Brother Bird", "GlobeBird": "Globe Bird",
}
STARTING_BIRDS = ("RedBird", "SmallBlueBird")
STARTING_EPISODE = "theme1"
EGGSTEROIDS = "bonus"

# filler item name -> (kind, game key); kinds are applied in-game by ap.lua
FILLER = {
    "Space Eagle": ("eagles", None),
    "Space Egg": ("powerup", "antenna"),
    "Flock of Birds": ("powerup", "flock"),
    "Pig Puffer": ("powerup", "inflate"),
}
# trap item name -> game key
TRAPS = {"Bird Swap Trap": "birdswap"}


def episode_item(name):
    return f"{name} Episode"


EPISODE_ITEMS = {folder: episode_item(name) for folder, name, _ in EPISODES}

item_name_to_id = {}
for i, (folder, name, _) in enumerate(EPISODES):
    item_name_to_id[EPISODE_ITEMS[folder]] = BASE_ID + i
for i, name in enumerate(BIRDS.values()):
    item_name_to_id[name] = BASE_ID + 100 + i
for i, name in enumerate(FILLER):
    item_name_to_id[name] = BASE_ID + 200 + i
for i, name in enumerate(TRAPS):
    item_name_to_id[name] = BASE_ID + 300 + i

item_name_groups = {
    "Episodes": set(EPISODE_ITEMS.values()),
    "Birds": set(BIRDS.values()),
    "Power-ups": {"Space Egg", "Flock of Birds", "Pig Puffer"},
    "Traps": set(TRAPS),
}


class AngryBirdsSpaceItem(Item):
    game = GAME


def classification(name):
    if name in FILLER:
        return ItemClassification.filler
    if name in TRAPS:
        return ItemClassification.trap
    return ItemClassification.progression
