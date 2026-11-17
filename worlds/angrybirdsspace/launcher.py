"""Angry Birds Space Archipelago launcher: install the mod, manage save profiles, start the game.

Everything on screen is drawn from the player's own game files (splash art, buttons, icons, fonts),
so it looks like the game and the apworld ships no game art.
"""
import os
import struct
import subprocess
import sys

from . import gamefiles

W, H = 960, 540  # design size; everything scales with the window
IMG = os.path.join("data", "images", "pc")
FONTS = os.path.join("data", "fonts", "1024x768")


# ---------------------------------------------------------------- game asset readers (stdlib only)
def read_sprites(dat_path):
    """KA3D/SPRT .dat -> {name: (x, y, w, h, px, py)}"""
    b = open(dat_path, "rb").read()
    p = 18 + 2 + struct.unpack_from(">H", b, 18)[0]
    cnt = struct.unpack_from(">H", b, p)[0]
    p += 2
    out = {}
    for _ in range(cnt):
        n = struct.unpack_from(">H", b, p)[0]
        name = b[p + 2:p + 2 + n].decode()
        p += 2 + n
        out[name] = struct.unpack_from(">4H2h", b, p)
        p += 12
    return out


def read_pvr(path):
    """PVR v2 RGBA4444 / RGB888 -> (w, h, rgba_or_rgb_bytes, colorfmt), rows top-down."""
    b = open(path, "rb").read()
    hl, h, w, _mips, flags = struct.unpack_from("<5I", b, 0)
    fmt = flags & 0xFF
    if fmt == 0x15:
        return w, h, b[hl:hl + w * h * 3], "rgb"
    assert fmt == 0x10, f"unsupported PVR format {fmt:#x}"
    d = b[hl:hl + w * h * 2]
    out = bytearray(w * h * 4)
    for i in range(w * h):
        v = d[2 * i] | d[2 * i + 1] << 8
        out[4 * i] = (v >> 12 & 15) * 17
        out[4 * i + 1] = (v >> 8 & 15) * 17
        out[4 * i + 2] = (v >> 4 & 15) * 17
        out[4 * i + 3] = (v & 15) * 17
    return w, h, bytes(out), "rgba"


def read_font_glyphs(dat_path):
    """Font .dat -> ({char: (x, y, w, h, baseline_from_top)}, spacing)"""
    b = open(dat_path, "rb").read()
    n = struct.unpack_from(">H", b, 0x12)[0]
    p = 0x14 + n
    _line_h, spacing, count = struct.unpack_from(">HhH", b, p)
    g = {}
    for i in range(count):
        ch, x, y, w, h, base = struct.unpack_from(">6h", b, p + 6 + 12 * i)
        g[chr(ch)] = (x, y, w, h, base)
    return g, spacing


def make_desktop_shortcut(game_dir):
    if getattr(sys, "frozen", False):
        target, args = sys.executable, '"Angry Birds Space Launcher"'
    else:
        import Utils
        target, args = sys.executable, f'"{os.path.join(Utils.local_path(), "Launcher.py")}" "Angry Birds Space Launcher"'
    icon = os.path.join(game_dir, "AngryBirdsSpace.exe")
    q = lambda v: "'" + v.replace("'", "''") + "'"
    script = ("$d=[Environment]::GetFolderPath('Desktop');"
              "$s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d 'Angry Birds Space Archipelago.lnk'));"
              f"$s.TargetPath={q(target)};$s.Arguments={q(args)};$s.WorkingDirectory={q(os.path.dirname(target))};"
              f"$s.IconLocation={q(icon)};$s.Save()")
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], check=True,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=60)


# ---------------------------------------------------------------- the app
def launch(*args):
    import kvui  # noqa: F401  (sets up Kivy the way the rest of Archipelago expects)
    from kivy.app import App
    from kivy.clock import Clock
    from kivy.core.image import Image as CoreImage
    from kivy.core.window import Window
    from kivy.graphics import Color, Line, Rectangle, RoundedRectangle
    from kivy.graphics.texture import Texture
    from kivy.uix.behaviors import ButtonBehavior
    from kivy.uix.floatlayout import FloatLayout
    from kivy.uix.textinput import TextInput
    from kivy.uix.widget import Widget
    from settings import get_settings

    def texture_from(w, h, data, fmt):
        n = 4 if fmt == "rgba" else 3
        rows = [data[y * w * n:(y + 1) * w * n] for y in range(h)]
        tex = Texture.create(size=(w, h), colorfmt=fmt)
        tex.blit_buffer(b"".join(reversed(rows)), colorfmt=fmt, bufferfmt="ubyte")  # Kivy is bottom-up
        return tex

    def region(tex, rect, bottom_up=True):
        """Sub-texture for a sprite rect given top-down; textures we blit ourselves are stored bottom-up."""
        x, y, w, h = rect[:4]
        return tex.get_region(x, tex.height - y - h if bottom_up else y, w, h)

    class Assets:
        def __init__(self, game):
            self.ok = os.path.exists(os.path.join(game, "AngryBirdsSpace.exe"))
            if not self.ok:
                return
            w, h, d, f = read_pvr(os.path.join(game, IMG, "SPLASHES_SHEET_2.pvr"))
            self.splash = texture_from(w, h, d, f)
            sheet = CoreImage(os.path.join(game, IMG, "BUTTONS_SHEET_1.png")).texture
            spr = read_sprites(os.path.join(game, IMG, "BUTTONS_SHEET_1.dat"))
            self.sprite = {k: region(sheet, v) for k, v in spr.items()}
            self.fonts = {}
            for key, name, overlap in (("head", "FONT_SPACE_BIG_HEADLINE", 4), ("basic", "FONT_SPACE_BASIC", 2)):
                w, h, d, f = read_pvr(os.path.join(game, FONTS, name + ".pvr"))
                tex = texture_from(w, h, d, f)
                glyphs, spacing = read_font_glyphs(os.path.join(game, FONTS, name + ".dat"))
                self.fonts[key] = ({c: (region(tex, g), g[2], g[3], g[4]) for c, g in glyphs.items()},
                                   max(overlap, -spacing))
            import pkgutil, io
            ov = pkgutil.get_data(__name__.rsplit(".", 1)[0], "mod/logo_overlay.png")
            ow, oh, orows = gamefiles.png_read(ov)
            self.overlay = texture_from(ow, oh, b"".join(bytes(r) for r in orows), "rgba")

    def text_width(assets, text, font, text_h):
        glyphs, overlap = assets.fonts[font]
        ref = glyphs.get("A")
        s = text_h / (ref[2] if ref else 40)
        w = 0
        for c in text:
            g = glyphs.get(c) or glyphs.get(c.upper())
            w += (g[1] - overlap) * s if g else text_h * 0.35
        return w, s

    def draw_text(assets, text, font, text_h, cx, cy, color=(1, 1, 1, 1)):
        """Draw text centred on (cx, cy) with the game's bitmap font glyphs (call inside a canvas block)."""
        glyphs, overlap = assets.fonts[font]
        total, s = text_width(assets, text, font, text_h)
        ref = glyphs.get("A")
        # baseline so a capital A is vertically centred; each glyph hangs from its own baseline offset
        baseline = cy - text_h / 2 + ((ref[2] - ref[3]) * s if ref else 0)
        x = cx - total / 2
        Color(*color)
        for c in text:
            g = glyphs.get(c) or glyphs.get(c.upper())
            if not g:
                x += text_h * 0.35
                continue
            tex, gw, gh, base = g
            Rectangle(texture=tex, pos=(x, baseline + base * s - gh * s), size=(gw * s, gh * s))
            x += (gw - overlap) * s

    class GameText(Widget):
        """A line of text in the game's own font."""
        def __init__(self, assets, text="", font="basic", height=24, color=(1, 1, 1, 1), **kw):
            kw.setdefault("size_hint", (None, None))
            super().__init__(**kw)
            self.assets, self.font, self.text_h, self.color = assets, font, height, color
            self.bind(pos=self.redraw, size=self.redraw)
            self.set(text)

        def set(self, text, color=None):
            self.text = str(text)
            if color:
                self.color = color
            self.redraw()

        def redraw(self, *a):
            self.canvas.clear()
            if self.assets.ok:
                with self.canvas:
                    draw_text(self.assets, self.text, self.font, self.text_h, self.center_x, self.center_y, self.color)

    class RoundButton(ButtonBehavior, Widget):
        """The game's green round button with an icon and a caption under it."""
        def __init__(self, app, icon, caption, on_press, big=False, **kw):
            kw.setdefault("size_hint", (None, None))
            super().__init__(**kw)
            self.app, self.icon, self.big, self.cb, self.caption = app, icon, big, on_press, caption
            self.cap_h = self.height * (0.17 if big else 0.18)
            self.bind(pos=self.redraw, size=self.redraw, state=self.redraw)
            self.redraw()

        def on_release(self):
            self.cb()

        def redraw(self, *a):
            self.canvas.clear()
            a = self.app.assets
            k = 0.93 if self.state == "down" else 1.0
            d = min(self.width, self.height - self.cap_h * 1.3) * k
            cx, cy = self.center_x, self.top - d / 2 - (1 - k) * d / 2
            with self.canvas:
                Color(1, 1, 1, 1)
                Rectangle(texture=a.sprite["BTN_BG_GREEN"], pos=(cx - d / 2, cy - d / 2), size=(d, d))
                icon = a.sprite.get(self.icon)
                if icon:
                    iw, ih = icon.size
                    f = d * (0.62 if self.big else 0.55) / max(iw, ih)
                    Rectangle(texture=icon, pos=(cx - iw * f / 2, cy - ih * f / 2), size=(iw * f, ih * f))
                draw_text(a, self.caption, "head" if self.big else "basic", self.cap_h, cx, self.y + self.cap_h / 2)

    class Panel(FloatLayout):
        """Dark rounded dialog panel, like the game's popups."""
        def __init__(self, **kw):
            kw.setdefault("size_hint", (None, None))
            super().__init__(**kw)
            self.bind(pos=self.redraw, size=self.redraw)
            self.redraw()

        def redraw(self, *a):
            self.canvas.before.clear()
            with self.canvas.before:
                Color(0, 0, 0, 0.55)
                Rectangle(pos=(0, 0), size=Window.size)
                Color(0.11, 0.2, 0.33, 0.97)
                RoundedRectangle(pos=self.pos, size=self.size, radius=[18])
                Color(0.75, 0.85, 0.95, 1)
                Line(rounded_rectangle=(self.x, self.y, self.width, self.height, 18), width=2.2)

        def on_touch_down(self, touch):
            super().on_touch_down(touch)
            return True  # modal

    class Row(ButtonBehavior, Widget):
        def __init__(self, app, name, active, selected, on_pick, **kw):
            kw.setdefault("size_hint", (None, None))
            super().__init__(**kw)
            self.label = GameText(app.assets, name + ("   (playing)" if active else ""), "basic", 22,
                                  color=(0.75, 1, 0.45, 1) if active else (1, 1, 1, 1))
            self.add_widget(self.label)
            self.selected, self.cb, self.name = selected, on_pick, name
            self.bind(pos=self.redraw, size=self.redraw)
            self.redraw()

        def on_release(self):
            self.cb(self.name)

        def redraw(self, *a):
            self.canvas.before.clear()
            with self.canvas.before:
                Color(1, 1, 1, 0.16 if self.selected else 0)
                RoundedRectangle(pos=self.pos, size=self.size, radius=[8])
            self.label.size = self.size
            self.label.pos = self.pos

    class LauncherApp(App):
        title = "Angry Birds Space Archipelago"

        def build(self):
            self.game = str(get_settings().angry_birds_space_options.game_path)
            self.assets = Assets(self.game)
            Window.size = (W, H)
            self.root_layout = FloatLayout()
            self.root_layout.bind(size=lambda *a: self.layout())
            self.status = None
            # ABS_LAUNCHER_PANEL=profiles|folder opens a panel at start (used to check layouts)
            start = {"profiles": lambda: self.profiles_panel(), "folder": lambda: self.folder_panel()}.get(
                os.environ.get("ABS_LAUNCHER_PANEL", ""), self.layout)
            Clock.schedule_once(lambda dt: start(), 0.2)
            Clock.schedule_interval(lambda dt: self.refresh_status(), 2)
            return self.root_layout

        # ---------------- screens
        def layout(self, panel=None):
            r = self.root_layout
            r.clear_widgets()
            r.canvas.before.clear()
            sw, sh = r.size
            s = sh / H
            if not self.assets.ok:
                self.folder_panel(first_run=True)
                return
            with r.canvas.before:  # splash art, cropped to fill
                Color(1, 1, 1, 1)
                tw, th = self.assets.splash.size
                k = max(sw / tw, sh / th)
                Rectangle(texture=self.assets.splash, pos=((sw - tw * k) / 2, (sh - th * k) / 2), size=(tw * k, th * k))
                ov = self.assets.overlay  # "ARCHIPELAGO" strip from our title logo, under the splash logo
                strip_h = ov.height * 0.30
                kk = (tw * k) * 0.29 / ov.width
                Rectangle(texture=ov.get_region(0, 0, ov.width, int(strip_h)),
                          pos=(sw / 2 - ov.width * kk / 2, sh - (th * k) * 0.34 - strip_h * kk),
                          size=(ov.width * kk, strip_h * kk))
            installed = os.path.exists(os.path.join(self.game, "data", "scripts", "ap.lua"))
            play = RoundButton(self, "ICON_ARROW_RIGHT", "PLAY", self.play, big=True, size=(150 * s, 190 * s))
            play.pos = (sw - 190 * s, 40 * s)
            r.add_widget(play)
            buttons = [("ICON_RECYCLE", "Update mod" if installed else "Install mod", self.install),
                       ("ICON_MENU", "Profiles", lambda: self.profiles_panel()),
                       ("ICON_OPTIONS", "Game folder", lambda: self.folder_panel()),
                       ("ICON_FULL_SCREEN", "Shortcut", self.shortcut)]
            for i, (icon, cap, cb) in enumerate(buttons):
                b = RoundButton(self, icon, cap, cb, size=(96 * s, 122 * s))
                b.pos = (24 * s + i * 112 * s, 18 * s)
                r.add_widget(b)
            self.status = GameText(self.assets, "", "basic", 20 * s, size=(sw, 30 * s), pos=(0, sh - 34 * s))
            r.add_widget(self.status)
            self.refresh_status()

        def refresh_status(self, note=None):
            if note:
                self.note = note
            if not self.status:
                return
            if getattr(self, "note", None):
                self.status.set(self.note)
                return
            prof = gamefiles.active_profile(self.game)
            if gamefiles.is_installed(self.game):
                mod = "Mod installed"
            elif os.path.exists(os.path.join(self.game, "data", "scripts", "ap.lua")):
                mod = "Mod update available"
            else:
                mod = "Mod not installed"
            run = "   Game running" if gamefiles.game_running() else ""
            self.status.set(f"{mod}   Profile: {prof}{run}")

        def say(self, text):
            self.note = text
            self.refresh_status()
            Clock.schedule_once(lambda dt: setattr(self, "note", None), 5)

        # ---------------- actions
        def install(self):
            try:
                gamefiles.install(self.game)
                self.say("Archipelago mod installed!")
            except Exception as e:
                self.say(f"Install failed: {e}")
            self.layout()

        def play(self):
            try:
                if not gamefiles.is_installed(self.game):
                    gamefiles.install(self.game)
                if gamefiles.game_running():
                    self.say("The game is already running")
                    return
                gamefiles.start_game(self.game)
                self.say("Starting Angry Birds Space...  connect with the Archipelago button")
            except Exception as e:
                self.say(f"Could not start: {e}")

        def shortcut(self):
            try:
                make_desktop_shortcut(self.game)
                self.say("Desktop shortcut created")
            except Exception as e:
                self.say(f"Shortcut failed: {e}")

        # ---------------- profiles
        def profiles_panel(self, selected=None, msg="", confirm_delete=False):
            self.layout()
            r = self.root_layout
            s = r.height / H
            names, active = gamefiles.list_profiles(self.game)
            selected = selected if selected in names else active
            p = Panel(size=(560 * s, 480 * s), pos=((r.width - 560 * s) / 2, (r.height - 480 * s) / 2 + 10 * s))
            r.add_widget(p)
            px, py = p.pos
            p.add_widget(GameText(self.assets, "PROFILES", "head", 40 * s, size=(560 * s, 50 * s), pos=(px, py + 415 * s)))
            p.add_widget(GameText(self.assets, "Each profile has its own save: stars, scores and AP progress",
                                  "basic", 15 * s, size=(560 * s, 22 * s), pos=(px, py + 392 * s)))
            pick = lambda n: self.profiles_panel(n)
            for i, n in enumerate(names[:6]):
                p.add_widget(Row(self, n, n == active, n == selected, pick,
                                 size=(380 * s, 34 * s), pos=(px + 60 * s, py + (345 - i * 38) * s)))
            name_in = TextInput(hint_text="New profile name", multiline=False, size_hint=(None, None), size=(250 * s, 36 * s),
                                pos=(px + 60 * s, py + 112 * s), font_size=18 * s, background_color=(0.05, 0.1, 0.18, 1),
                                foreground_color=(1, 1, 1, 1), cursor_color=(1, 1, 1, 1))
            p.add_widget(name_in)

            def create():
                try:
                    n = gamefiles.new_profile(self.game, name_in.text)
                    self.profiles_panel(n, f"Created '{n}'")
                except Exception as e:
                    self.profiles_panel(selected, str(e))

            def use():
                try:
                    gamefiles.switch_profile(self.game, selected)
                    self.profiles_panel(selected, f"Now playing as '{selected}'")
                except Exception as e:
                    self.profiles_panel(selected, str(e))

            def delete():
                if not confirm_delete:
                    self.profiles_panel(selected, f"Press delete again to erase '{selected}' for good", True)
                    return
                try:
                    gamefiles.delete_profile(self.game, selected)
                    self.profiles_panel(None, f"Deleted '{selected}'")
                except Exception as e:
                    self.profiles_panel(selected, str(e))

            name_in.bind(on_text_validate=lambda *a: create())
            # "New" sits next to the name box; the rest form the bottom row
            for icon, cap, cb, x, y in [("ICON_NEXT", "New", create, 462, 98), ("ICON_CHECK", "Play as", use, 110, 6),
                                        ("ICON_X", "Delete", delete, 243, 6), ("ICON_BACK", "Back", self.layout, 376, 6)]:
                b = RoundButton(self, icon, cap, cb, size=(74 * s, 96 * s))
                b.pos = (px + x * s, py + y * s)
                p.add_widget(b)
            if msg:
                p.add_widget(GameText(self.assets, msg, "basic", 16 * s, size=(560 * s, 22 * s), pos=(px, py + 82 * s),
                                      color=(1, 0.85, 0.4, 1)))

        # ---------------- game folder
        def folder_panel(self, msg="", first_run=False, confirm_uninstall=False):
            r = self.root_layout
            if not first_run:
                self.layout()
            s = r.height / H
            p = Panel(size=(640 * s, 300 * s), pos=((r.width - 640 * s) / 2, (r.height - 300 * s) / 2))
            r.add_widget(p)
            px, py = p.pos
            ok = self.assets.ok
            title = GameText(self.assets, "GAME FOLDER", "head", 36 * s, size=(640 * s, 44 * s), pos=(px, py + 240 * s)) \
                if ok else None
            if title:
                p.add_widget(title)
            path_in = TextInput(text=self.game, multiline=False, size_hint=(None, None), size=(560 * s, 36 * s), pos=(px + 40 * s, py + 180 * s),
                                font_size=16 * s, background_color=(0.05, 0.1, 0.18, 1), foreground_color=(1, 1, 1, 1),
                                cursor_color=(1, 1, 1, 1))
            p.add_widget(path_in)

            def save():
                new = path_in.text.strip().strip('"')
                if not os.path.exists(os.path.join(new, "AngryBirdsSpace.exe")):
                    self.folder_panel("That folder has no AngryBirdsSpace.exe", first_run)
                    return
                st = get_settings()
                st.angry_birds_space_options.game_path = new
                st.save()
                self.game = new
                self.assets = Assets(new)
                self.layout()
                self.say("Game folder saved")

            def uninstall():
                if not confirm_uninstall:
                    self.folder_panel("Press uninstall again to restore the original game files", first_run, True)
                    return
                try:
                    gamefiles.uninstall(self.game)
                    self.layout()
                    self.say("Original game files restored")
                except Exception as e:
                    self.folder_panel(f"Uninstall failed: {e}", first_run)

            if ok:
                acts = [("ICON_CHECK", "Save", save), ("ICON_X", "Uninstall mod", uninstall), ("ICON_BACK", "Back", self.layout)]
                for i, (icon, cap, cb) in enumerate(acts):
                    b = RoundButton(self, icon, cap, cb, size=(80 * s, 104 * s))
                    b.pos = (px + (110 + i * 170) * s, py + 30 * s)
                    p.add_widget(b)
                if msg:
                    p.add_widget(GameText(self.assets, msg, "basic", 16 * s, size=(640 * s, 22 * s), pos=(px, py + 146 * s),
                                          color=(1, 0.85, 0.4, 1)))
            else:  # no game assets to draw with yet: plain controls
                from kivy.uix.button import Button
                from kivy.uix.label import Label
                p.add_widget(Label(size_hint=(None, None), text="Where is Angry Birds Space installed?\n(the folder with AngryBirdsSpace.exe)\n" + msg,
                                   halign="center", size=(640 * s, 80 * s), pos=(px, py + 220 * s), font_size=18 * s))
                p.add_widget(Button(text="Save", size_hint=(None, None), size=(160 * s, 44 * s), pos=(px + 240 * s, py + 60 * s),
                                    on_release=lambda *a: save()))

    LauncherApp().run()
