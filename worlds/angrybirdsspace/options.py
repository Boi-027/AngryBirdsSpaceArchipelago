from dataclasses import dataclass
from Options import Choice, DeathLink, DefaultOnToggle, PerGameCommonOptions, Range, Toggle


class Goal(Choice):
    """What you need to do to finish.
    Boss Rush: defeat all 8 episode bosses (Pig Bang to Beak Impact 1).
    Level Count: clear the number of levels set in Levels For Goal.
    Star Hunt: collect the number of stars set in Stars For Goal (best stars per level, all episodes)."""
    display_name = "Goal"
    option_boss_rush = 0
    option_level_count = 1
    option_star_hunt = 2
    default = 0


class LevelsForGoal(Range):
    """Levels to clear for the Level Count goal (290 levels exist, 309 with Eggsteroids)."""
    display_name = "Levels For Goal"
    range_start = 10
    range_end = 309
    default = 120


class StarsForGoal(Range):
    """Stars to collect for the Star Hunt goal (each level gives up to 3)."""
    display_name = "Stars For Goal"
    range_start = 30
    range_end = 900
    default = 300


class ThreeStarChecks(Toggle):
    """Three-starring a level is also a check (doubles the number of level locations)."""
    display_name = "Three Star Checks"


class IncludeEggsteroids(DefaultOnToggle):
    """Eggsteroids becomes a randomized episode with its own unlock item and checks.
    When off, Eggsteroids works like the normal game and has no checks."""
    display_name = "Include Eggsteroids"


class TrapChance(Range):
    """Percent of filler items replaced by Bird Swap Traps (your next bird is swapped for another
    bird from the same level)."""
    display_name = "Trap Chance"
    range_start = 0
    range_end = 100
    default = 10


@dataclass
class AngryBirdsSpaceOptions(PerGameCommonOptions):
    goal: Goal
    levels_for_goal: LevelsForGoal
    stars_for_goal: StarsForGoal
    three_star_checks: ThreeStarChecks
    include_eggsteroids: IncludeEggsteroids
    trap_chance: TrapChance
    death_link: DeathLink
