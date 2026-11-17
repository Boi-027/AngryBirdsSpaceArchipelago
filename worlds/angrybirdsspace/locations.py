from BaseClasses import Location
from .data import EPISODES
from .items import BASE_ID, GAME

STARS_OFFSET = 50000
COMPLETE_NUMBER = 99  # "<Episode> Complete" uses the id slot after the levels


class AngryBirdsSpaceLocation(Location):
    game = GAME


def clear_name(episode, number):
    return f"{episode} {number}"


def stars_name(episode, number):
    return f"{episode} {number} Three Stars"


def complete_name(episode):
    return f"{episode} Complete"


# one row per playable level: (folder, episode name, level file, number shown in game, birds, is_boss, ids)
LEVELS = []
# folder -> (episode name, "Complete" location id)
EPISODE_COMPLETE = {}
for e, (folder, name, rows) in enumerate(EPISODES):
    for level, _idx, number, birds, boss in rows:
        clear_id = BASE_ID + e * 100 + number
        LEVELS.append((folder, name, level, number, birds, boss, clear_id, clear_id + STARS_OFFSET))
    EPISODE_COMPLETE[folder] = (name, BASE_ID + e * 100 + COMPLETE_NUMBER)

location_name_to_id = {}
for folder, name, level, number, birds, boss, cid, sid in LEVELS:
    location_name_to_id[clear_name(name, number)] = cid
    location_name_to_id[stars_name(name, number)] = sid
for folder, (name, lid) in EPISODE_COMPLETE.items():
    location_name_to_id[complete_name(name)] = lid

location_name_groups = {
    name: {clear_name(n, num) for f, n, _l, num, *_ in LEVELS if n == name} | {complete_name(name)}
    for _f, name, _r in EPISODES
}
location_name_groups["Bosses"] = {clear_name(n, num) for f, n, l, num, b, boss, *_ in LEVELS if boss}
location_name_groups["Episode Completions"] = {complete_name(n) for n, _ in EPISODE_COMPLETE.values()}
