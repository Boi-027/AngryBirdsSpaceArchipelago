"""Angry Birds Space client: bridges the AP server and the modded game through two files.

  ap_in.lua    (game folder, plain Lua)   client -> game: unlocks, consumables, messages, DeathLink
  ap_state.lua (save folder, encrypted)   game -> client: cleared / three-starred levels, deaths
"""
import asyncio
import os
import re
from collections import Counter

from CommonClient import ClientCommandProcessor, CommonContext, get_base_parser, gui_enabled, logger, server_loop
from NetUtils import ClientStatus

from . import gamefiles
from . import included_levels, level_open
from .items import BIRDS, EPISODE_ITEMS, FILLER, GAME, TRAPS
from .locations import EPISODE_COMPLETE
from .options import Goal

MAX_MESSAGES = 12


def parse_state(text):
    """Read the few fields we need from the game's saveLuaFile output."""
    def block(name):
        m = re.search(rf"^{name} = {{(.*?)^}}", text, re.S | re.M)
        return set(re.findall(r'\[?"?([\w.-]+)"?\]?\s*=\s*true', m.group(1))) if m else set()
    seed = re.search(r'^seed = "(.*)"\s*$', text, re.M)
    def num(name):  # the game writes numbers as float32 text, e.g. 12 or 1.5e+001
        m = re.search(rf"^{name} = ([-+.\de]+)", text, re.M)
        return int(round(float(m.group(1)))) if m else 0
    m = re.search(r"^stars = \{(.*?)^\}", text, re.S | re.M)
    stars = {k: int(round(float(v))) for k, v in re.findall(r'\[?"?([\w.-]+)"?\]?\s*=\s*([-+.\de]+)', m.group(1))} if m else {}
    return {"seed": seed.group(1) if seed else None, "cleared": block("cleared"), "perfect": block("perfect"),
            "stars": stars, "deaths": num("deaths"), "msgSeen": num("msgSeen"), "deathSeen": num("deathSeen")}


class AngryBirdsSpaceCommandProcessor(ClientCommandProcessor):
    def _cmd_game_path(self, path: str = ""):
        """Show or set the Angry Birds Space folder (the one with AngryBirdsSpace.exe)."""
        if path:
            self.ctx.set_game_dir(path)
        logger.info(f"Game folder: {self.ctx.game_dir}")

    def _cmd_install_mod(self):
        """(Re)install the Archipelago mod into the game folder."""
        self.ctx.install_mod(force=True)

    def _cmd_uninstall_mod(self):
        """Restore the original game files."""
        gamefiles.uninstall(self.ctx.game_dir)
        logger.info("Original game files restored.")


class AngryBirdsSpaceContext(CommonContext):
    game = GAME
    items_handling = 0b111
    command_processor = AngryBirdsSpaceCommandProcessor

    def __init__(self, server_address, password):
        super().__init__(server_address, password)
        from settings import get_settings
        self.game_dir = str(get_settings().angry_birds_space_options.game_path)
        self.slot_data = {}
        self.messages = []        # [{id, text}] sent to the game
        self.pending = []         # texts waiting for an id
        self.msg_next = None      # ids continue from the game's msgSeen: small ints survive float32
        self.death = None
        self.pending_death = None
        self.death_next = None
        self.last_deaths = None
        self.last_written = None
        self.goal_sent = False
        self.room_seed = None
        self.helper = False       # started by the game through ap_helper.lnk: no windows, no prompts
        self.req = 0              # connect-screen request number, echoed so the game ignores stale status
        self.status = None

    def set_game_dir(self, path):
        from settings import get_settings
        get_settings().angry_birds_space_options.game_path = path
        get_settings().save()
        self.game_dir = path
        self.install_mod()

    def install_mod(self, force=False):
        try:
            if force or not gamefiles.is_installed(self.game_dir):
                gamefiles.install(self.game_dir)
                logger.info("Archipelago mod installed. Restart the game if it is running.")
        except Exception as e:
            logger.error(f"Could not install the mod into '{self.game_dir}': {e}. Use /game_path <folder>.")

    async def server_auth(self, password_requested: bool = False):
        if password_requested and not self.password:
            if self.helper:
                self.set_status("This room needs a password", toast=True)
                return
            await super().server_auth(password_requested)
        await self.get_username()
        await self.send_connect()

    def on_package(self, cmd, args):
        if cmd == "RoomInfo":
            self.room_seed = args["seed_name"]  # ctx.seed_name is not reliably set on every AP version
        elif cmd == "ConnectionRefused":
            self.set_status("Connection refused: " + ", ".join(args.get("errors", [])), toast=True)
        elif cmd == "Connected":
            self.set_status(f"Connected as {self.auth}", toast=True)
            self.slot_data = args["slot_data"]
            self.goal_sent = False
            self.last_deaths = None
            if self.slot_data.get("death_link"):
                asyncio.create_task(self.update_death_link(True))

    def set_status(self, text, toast=False):
        """Shown on the in-game connect screen (and as a notification when toast is set)."""
        if text == self.status:
            return
        self.status = text
        logger.info(text)
        try:
            path = os.path.join(self.game_dir, "ap_status.lua")
            with open(path + ".tmp", "w") as f:
                f.write("apStatus = " + gamefiles.lua_value({"text": text, "toast": toast, "req": self.req}) + "\n")
            os.replace(path + ".tmp", path)
        except OSError:
            pass

    def add_message(self, text):
        self.pending.append(text)

    def on_print_json(self, args):
        super().on_print_json(args)
        if args.get("type") != "ItemSend" or not self.slot:
            return
        item, to = args["item"], args["receiving"]
        name = self.item_names.lookup_in_slot(item.item, to)
        if to == self.slot and item.player == self.slot:
            self.add_message(f"You found your {name}!")
        elif to == self.slot:
            self.add_message(f"Received {name} from {self.player_names[item.player]}")
        elif item.player == self.slot:
            self.add_message(f"Sent {name} to {self.player_names[to]}")

    def on_deathlink(self, data):
        super().on_deathlink(data)
        self.pending_death = data.get("source", "Someone")

    def make_gui(self):
        ui = super().make_gui()
        ui.base_title = "Angry Birds Space Client"
        return ui

    # ------------------------------------------------------------ game sync
    def sync(self):
        if not self.slot or not self.room_seed:
            return
        seed = f"{self.room_seed}-{self.slot}"
        state_path = os.path.join(self.game_dir, gamefiles.REMOTE_DIR, gamefiles.STATE_FILE)
        st = None
        if os.path.exists(state_path):
            st = parse_state(gamefiles.decrypt_save(open(state_path, "rb").read()))
            if st["seed"] != seed:
                st = None  # game has not picked up this seed yet; it starts its counters at 0
        if self.msg_next is None:
            self.msg_next = st["msgSeen"] if st else 0
            self.death_next = st["deathSeen"] if st else 0
        for text in self.pending:
            self.msg_next += 1
            self.messages.append({"id": self.msg_next, "text": text})
        self.pending.clear()
        del self.messages[:-MAX_MESSAGES]
        if self.pending_death:
            self.death_next += 1
            self.death = {"id": self.death_next, "source": self.pending_death}
            self.pending_death = None

        levels = included_levels(bool(self.slot_data.get("include_eggsteroids")))
        have = Counter(self.item_names.lookup_in_slot(i.item, self.slot) for i in self.items_received)
        has = lambda n: have[n] > 0
        needs = {}  # locked level -> what is missing, shown when the locked level is clicked
        for f, _e, lvl, _n, birds, *_ in levels:
            missing = [EPISODE_ITEMS[f]] * (not has(EPISODE_ITEMS[f])) + [BIRDS[b] for b in birds if not has(BIRDS[b])]
            if missing:
                needs[lvl] = ", ".join(missing)
        out = {
            "seed": seed,
            "slot": self.player_names[self.slot],
            "managed": {f: True for f in dict.fromkeys(row[0] for row in levels)},
            "episodes": {f: True for f, n in EPISODE_ITEMS.items() if has(n)},
            "open": {lvl: True for f, _e, lvl, _n, birds, *_ in levels if level_open(has, f, birds)},
            "needs": needs,
            "episodeItems": {f: EPISODE_ITEMS[f] for f in dict.fromkeys(row[0] for row in levels)},
            "eagles": have["Space Eagle"],
            "powerups": {key: have[name] for name, (kind, key) in FILLER.items() if kind == "powerup"},
            "traps": {key: have[name] for name, key in TRAPS.items()},
            "messages": self.messages,
            "deathlinkEnabled": bool(self.slot_data.get("death_link")),
        }
        if self.death:
            out["deathlink"] = self.death
        text = "apIn = " + gamefiles.lua_value(out) + "\n"
        if text != self.last_written:
            path = os.path.join(self.game_dir, gamefiles.IN_FILE)
            with open(path + ".tmp", "w") as f:
                f.write(text)
            os.replace(path + ".tmp", path)
            if self.last_written is None:
                logger.info("Sending your items to the game.")
            self.last_written = text

        if not st:
            return

        cleared = st["cleared"]
        checks = {cid for f, _e, lvl, _n, _b, _boss, cid, _s in levels if lvl in cleared}
        if self.slot_data.get("three_star_checks"):
            checks |= {sid for f, _e, lvl, _n, _b, _boss, _c, sid in levels if lvl in st["perfect"]}
        for folder in out["managed"]:
            if all(lvl in cleared for f, _e, lvl, *_ in levels if f == folder):
                checks.add(EPISODE_COMPLETE[folder][1])
        new = checks & self.missing_locations
        if new:
            asyncio.create_task(self.send_msgs([{"cmd": "LocationChecks", "locations": sorted(new)}]))

        if self.last_deaths is not None and st["deaths"] > self.last_deaths and "DeathLink" in self.tags:
            asyncio.create_task(self.send_death(f"{self.player_names[self.slot]} was outsmarted by the pigs."))
        self.last_deaths = st["deaths"]

        if not self.goal_sent:
            goal = self.slot_data.get("goal")
            names = {lvl for _f, _e, lvl, *_ in levels}
            if goal == Goal.option_boss_rush:
                done = all(lvl in cleared for _f, _e, lvl, _n, _b, boss, *_ in levels if boss)
            elif goal == Goal.option_star_hunt:
                done = sum(min(3, n) for lvl, n in st["stars"].items() if lvl in names) >= self.slot_data["stars_for_goal"]
            else:
                done = len(cleared & names) >= self.slot_data.get("levels_for_goal", 0)
            if done:
                self.goal_sent = True
                self.add_message("Goal complete! The Space Pigs are defeated!")
                asyncio.create_task(self.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}]))


async def game_loop(ctx: AngryBirdsSpaceContext):
    ctx.install_mod()
    logger.info(f"Watching game folder: {ctx.game_dir}")
    while not ctx.exit_event.is_set():
        try:
            ctx.sync()
        except Exception as e:
            logger.error(f"Game sync failed: {e}")
        await asyncio.sleep(1)


def read_connect_request(game_dir):
    """The connect screen's request, saved by the game with saveLuaFile (encrypted)."""
    path = os.path.join(game_dir, gamefiles.REMOTE_DIR, "ap_connect.lua")
    if not os.path.exists(path):
        return None
    text = gamefiles.decrypt_save(open(path, "rb").read())
    out = {}
    for k, v in re.findall(r'^(\w+) = (.*)$', text, re.M):
        v = v.strip()
        if v.startswith('"') and v.endswith('"'):
            v = re.sub(r'\\(.)', r'\1', v[1:-1])
        out[k] = v
    return out


async def helper_loop(ctx: AngryBirdsSpaceContext):
    """Follow the in-game connect screen; quit when the game has been closed for a while."""
    last_req, since, gone = None, 0.0, 0
    while not ctx.exit_event.is_set():
        try:
            req = read_connect_request(ctx.game_dir)
            if req and req.get("slot") and (req.get("req"), req.get("slot"), req.get("host")) != last_req:
                last_req = (req.get("req"), req.get("slot"), req.get("host"))
                ctx.req = int(float(req.get("req") or 0))
                ctx.auth = req["slot"]
                ctx.password = req.get("password") or None
                address = f'{req.get("host") or "archipelago.gg"}:{req.get("port") or 38281}'
                ctx.status = None
                ctx.set_status(f"Connecting to {address}...")
                since = 0.0
                asyncio.create_task(ctx.connect(address))
            since += 1
            if not ctx.slot and since == 15 and ctx.status and ctx.status.startswith("Connecting"):
                ctx.set_status("Could not reach the server. Check the address and port.", toast=True)
            gone = 0 if gamefiles.game_running() else gone + 1
            if gone >= 15:
                logger.info("Game closed, helper exiting.")
                ctx.exit_event.set()
        except Exception as e:
            logger.error(f"Helper: {e}")
        await asyncio.sleep(1)


def launch(*args):
    async def main(args):
        ctx = AngryBirdsSpaceContext(args.connect, args.password)
        ctx.auth = args.name
        if args.game_path:
            ctx.game_dir = args.game_path
        tasks =[asyncio.create_task(game_loop(ctx), name="game sync")]
        if args.helper:
            ctx.helper = True
            tasks.append(asyncio.create_task(helper_loop(ctx), name="helper"))
        else:
            ctx.server_task = asyncio.create_task(server_loop(ctx), name="server loop")
            if gui_enabled and not args.nogui:
                ctx.run_gui()
            ctx.run_cli()
        await ctx.exit_event.wait()
        for t in tasks:
            t.cancel()
        await ctx.shutdown()

    parser = get_base_parser(description="Angry Birds Space Client")
    if "--name" not in parser._option_string_actions:
        parser.add_argument("--name", default=None, help="Slot name to connect as")
    if "--nogui" not in parser._option_string_actions:
        parser.add_argument("--nogui", action="store_true", help="Run without the window")
    parser.add_argument("--helper", action="store_true", help="Hidden helper started by the game's connect screen")
    parser.add_argument("--game_path", default=None, help="Use this game folder for this run only")
    parsed, _ = parser.parse_known_args(args)
    if parsed.helper:
        import ctypes
        # one helper at a time; the running one picks up new requests from the connect screen
        launch.mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\AngryBirdsSpaceAPHelper")
        if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            return
    import colorama
    colorama.just_fix_windows_console()
    asyncio.run(main(parsed))
