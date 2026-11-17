# Angry Birds Space Archipelago Setup

## Requirements

- Angry Birds Space for PC (the Rovio PC release with `AngryBirdsSpace.exe`)
- Archipelago 0.6.4 or newer
- `angrybirdsspace.apworld`

## Install

1. Put `angrybirdsspace.apworld` in Archipelago's `custom_worlds` folder.
2. In `host.yaml` set `angry_birds_space_options: game_path:` to your game folder, or run
   `/game_path <folder>` in the client later.
3. Open the Archipelago Launcher and start **Angry Birds Space Client** once. It installs the mod
   (originals are kept in `<game folder>/ap_backup`; `/uninstall_mod` restores them). After that you can
   connect from inside the game.

## Play (everything in-game)

1. Start the game. The title screen shows the Archipelago logo when the mod is active.
2. Click the round **Archipelago** button (bottom left of the main menu).
3. Fill in Server, Port, Slot name and Password and press the check button.
   - **Ctrl+V** pastes; pasting `archipelago.gg:38281` into Server fills the port too.
   - The game has no `.` key, so **Space types a dot** in the Server field. **Shift** gives capitals and `_`.
   - Tab / arrow keys move between fields, Enter connects, Esc closes.
4. The connection runs in a hidden helper; the game remembers it and reconnects automatically next time.

You can still use the **Angry Birds Space Client** from the Archipelago Launcher instead (it shows the
full server log and accepts `!hint` and other commands).

AP progress is stored per seed, so your normal highscores are never counted as checks, and they are left
untouched.
