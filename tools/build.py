"""Build the apworld: encrypt the game scripts, render the logo overlay, zip worlds/angrybirdsspace.

usage: build.py   ->  build/angrybirdsspace.apworld
"""
import os, shutil, sys, zipfile
HERE = os.path.dirname(os.path.abspath(__file__))
MOD = os.path.dirname(HERE)
GAME = os.path.join(os.path.dirname(MOD), "Angry Birds Space")
sys.path.insert(0, HERE)
import abcrypt, make_logo

WORLD = os.path.join(MOD, "worlds", "angrybirdsspace")
WRAPPER = b"""-- Archipelago: run the original game logic, then the AP hooks
native.loadLuaScript("gamelogic_orig.lua")
native.loadLuaScript("ap.lua")
"""

out = os.path.join(WORLD, "mod")
os.makedirs(out, exist_ok=True)
open(os.path.join(out, "gamelogic.lua"), "wb").write(abcrypt.encrypt(WRAPPER, "gamelogic.lua"))
open(os.path.join(out, "ap.lua"), "wb").write(abcrypt.encrypt(open(os.path.join(MOD, "game", "ap.lua"), "rb").read(), "ap.lua"))
img = os.path.join(MOD, "build", "images")
make_logo.main(os.path.join(MOD, "backup", "data", "images", "pc"), os.path.join(GAME, "data", "fonts", "1024x768"), img)
for f in ("logo_overlay.png", "ap_menu_icon.png", "ap_launcher_icon.png"):
    shutil.copy2(os.path.join(img, f), os.path.join(out, f))

# Angry Birds Space Archipelago.exe: compiled with the C# compiler that ships with Windows
import subprocess
csc = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Microsoft.NET", "Framework64", "v4.0.30319", "csc.exe")
exe = os.path.join(out, "AngryBirdsSpaceArchipelago.exe")
subprocess.run([csc, "/nologo", "/target:winexe", "/optimize+", f"/win32icon:{os.path.join(img, 'ap_launcher_icon.ico')}",
                "/r:System.Windows.Forms.dll", "/r:System.Drawing.dll", f"/out:{exe}",
                os.path.join(HERE, "exe", "Launcher.cs")], check=True)
shutil.copy2(exe, os.path.join(MOD, "build", "Angry Birds Space Archipelago.exe"))

dst = os.path.join(MOD, "build", "angrybirdsspace.apworld")
with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as z:
    for root, dirs, files in os.walk(WORLD):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in files:
            p = os.path.join(root, f)
            rel = os.path.relpath(p, WORLD)
            # the manifest sits at the zip root, the package in its folder
            z.write(p, rel if rel == "archipelago.json" else os.path.join("angrybirdsspace", rel))
print("built", dst)
