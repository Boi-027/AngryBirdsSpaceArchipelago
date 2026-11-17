"""Self-check for the save-profile functions in gamefiles.py, on a throwaway folder."""
import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "worlds", "angrybirdsspace"))
import gamefiles as g

game = tempfile.mkdtemp()
remote = os.path.join(game, g.REMOTE_DIR)
os.makedirs(remote)
open(os.path.join(remote, "settings.lua"), "w").write("old")
open(os.path.join(remote, "highscores.lua"), "w").write("old scores")
open(os.path.join(remote, "steam_cache.bin"), "w").write("not a save")  # must be left alone

assert g.list_profiles(game) == (["Default"], "Default")
g.new_profile(game, "Seed 2")
for bad in ("", "a/b", "x" * 30, "Seed 2"):
    try:
        g.new_profile(game, bad)
        raise AssertionError(f"accepted {bad!r}")
    except ValueError:
        pass

g.switch_profile(game, "Seed 2")  # fresh profile: no saves live
assert g.active_profile(game) == "Seed 2"
assert sorted(os.listdir(remote)) == ["steam_cache.bin"]
open(os.path.join(remote, "settings.lua"), "w").write("new")

g.switch_profile(game, "Default")  # old saves come back, new ones are stashed
assert open(os.path.join(remote, "settings.lua")).read() == "old"
assert open(os.path.join(remote, "highscores.lua")).read() == "old scores"
assert open(os.path.join(game, g.PROFILES_DIR, "Seed 2", "settings.lua")).read() == "new"

try:
    g.delete_profile(game, "Default")
    raise AssertionError("deleted the active profile")
except ValueError:
    pass
g.delete_profile(game, "Seed 2")
assert g.list_profiles(game) == (["Default"], "Default")
print("profiles ok")
