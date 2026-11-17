"""Angry Birds Space (PC) for Archipelago."""
import settings
from BaseClasses import Region, Tutorial
from worlds.AutoWorld import WebWorld, World
from worlds.LauncherComponents import Component, Type, components, launch_subprocess

from .items import (BIRDS, EGGSTEROIDS, EPISODE_ITEMS, FILLER, GAME, STARTING_BIRDS, STARTING_EPISODE, TRAPS,
                    AngryBirdsSpaceItem, classification, item_name_groups, item_name_to_id)
from .locations import (EPISODE_COMPLETE, LEVELS, AngryBirdsSpaceLocation, clear_name, complete_name,
                        location_name_groups, location_name_to_id, stars_name)
from .options import AngryBirdsSpaceOptions, Goal


def level_open(has, folder, birds):
    """Shared by generation and the client: a level is playable with its episode and every bird it uses."""
    return has(EPISODE_ITEMS[folder]) and all(has(BIRDS[b]) for b in birds)


def included_levels(include_eggsteroids):
    """Level rows that are part of the randomizer (shared by generation and the client)."""
    return [row for row in LEVELS if include_eggsteroids or row[0] != EGGSTEROIDS]


def launch_client(*args):
    from .client import launch
    launch_subprocess(launch, name="AngryBirdsSpaceClient", args=args)


def launch_launcher(*args):
    from .launcher import launch
    launch_subprocess(launch, name="AngryBirdsSpaceLauncher", args=args)


components.append(Component("Angry Birds Space Client", func=launch_client, component_type=Type.CLIENT))
components.append(Component("Angry Birds Space Launcher", func=launch_launcher, component_type=Type.TOOL,
                            description="Install the mod, manage save profiles and start the game."))


class AngryBirdsSpaceSettings(settings.Group):
    class GamePath(settings.UserFolderPath):
        """Angry Birds Space folder (the one containing AngryBirdsSpace.exe)"""
        description = "Angry Birds Space game folder"

    game_path: GamePath = GamePath("C:/Program Files (x86)/Steam/steamapps/common/Angry Birds Space")


class AngryBirdsSpaceWeb(WebWorld):
    theme = "partyTime"
    tutorials = [Tutorial("Setup Guide", "How to install the mod and connect.", "English", "setup_en.md",
                          "setup/en", ["Archipelago community"])]


class AngryBirdsSpaceWorld(World):
    """Slingshot birds through gravity wells to save the eggs from the Space Pigs.
    Episodes and birds are scattered across the multiworld."""
    game = GAME
    web = AngryBirdsSpaceWeb()
    options_dataclass = AngryBirdsSpaceOptions
    options: AngryBirdsSpaceOptions
    settings_key = "angry_birds_space_options"
    settings: AngryBirdsSpaceSettings
    item_name_to_id = item_name_to_id
    location_name_to_id = location_name_to_id
    item_name_groups = item_name_groups
    location_name_groups = location_name_groups

    def generate_early(self):
        self.levels = included_levels(bool(self.options.include_eggsteroids))
        self.folders = list(dict.fromkeys(row[0] for row in self.levels))
        # goals can never ask for more than exists
        self.levels_for_goal = min(self.options.levels_for_goal.value, len(self.levels))
        self.stars_for_goal = min(self.options.stars_for_goal.value, 3 * len(self.levels))

    def create_item(self, name):
        return AngryBirdsSpaceItem(name, classification(name), self.item_name_to_id[name], self.player)

    def create_regions(self):
        menu = Region("Menu", self.player, self.multiworld)
        self.multiworld.regions.append(menu)
        p = self.player
        rule_for = lambda f, b: lambda state: level_open(lambda n: state.has(n, p), f, b)

        def add(name, lid, rule):
            loc = AngryBirdsSpaceLocation(p, name, lid, menu)
            loc.access_rule = rule
            menu.locations.append(loc)

        for folder, ep, level, number, birds, boss, cid, sid in self.levels:
            add(clear_name(ep, number), cid, rule_for(folder, birds))
            if self.options.three_star_checks:
                add(stars_name(ep, number), sid, rule_for(folder, birds))
        for folder in self.folders:
            rows = [(f, b) for f, _e, _l, _n, b, *_ in self.levels if f == folder]
            name, lid = EPISODE_COMPLETE[folder]
            add(complete_name(name), lid,
                (lambda rs: lambda state: all(level_open(lambda n: state.has(n, p), f, b) for f, b in rs))(rows))

        open_count = lambda state: sum(level_open(lambda n: state.has(n, p), f, b) for f, _e, _l, _n, b, *_ in self.levels)
        if self.options.goal == Goal.option_boss_rush:
            bosses = [(f, b) for f, _e, _l, _n, b, boss, *_ in self.levels if boss]
            self.multiworld.completion_condition[p] = lambda state: all(
                level_open(lambda n: state.has(n, p), f, b) for f, b in bosses)
        elif self.options.goal == Goal.option_level_count:
            need = self.levels_for_goal
            self.multiworld.completion_condition[p] = lambda state: open_count(state) >= need
        else:
            need = self.stars_for_goal
            self.multiworld.completion_condition[p] = lambda state: 3 * open_count(state) >= need

    def create_items(self):
        for b in STARTING_BIRDS:
            self.multiworld.push_precollected(self.create_item(BIRDS[b]))
        self.multiworld.push_precollected(self.create_item(EPISODE_ITEMS[STARTING_EPISODE]))
        pool = [self.create_item(EPISODE_ITEMS[f]) for f in self.folders if f != STARTING_EPISODE]
        pool += [self.create_item(BIRDS[b]) for b in BIRDS if b not in STARTING_BIRDS]
        total = len(self.multiworld.get_unfilled_locations(self.player))
        pool += [self.create_item(self.get_filler_item_name()) for _ in range(total - len(pool))]
        self.multiworld.itempool += pool

    def get_filler_item_name(self):
        if self.random.randint(1, 100) <= self.options.trap_chance.value:
            return self.random.choice(list(TRAPS))
        return self.random.choice(list(FILLER))

    def fill_slot_data(self):
        return {
            "goal": self.options.goal.value,
            "levels_for_goal": self.levels_for_goal,
            "stars_for_goal": self.stars_for_goal,
            "three_star_checks": self.options.three_star_checks.value,
            "include_eggsteroids": self.options.include_eggsteroids.value,
            "death_link": self.options.death_link.value,
        }
