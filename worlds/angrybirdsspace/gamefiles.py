"""Game-side file handling for the Angry Birds Space client, using only the standard library
(the frozen Archipelago install has no crypto or imaging packages).

- decrypt_save(): the game's save files (AES-256-CBC, zero IV, newline padded)
- install()/uninstall(): put the mod into a game folder, keeping a pristine backup
- the title logo is rebuilt from the player's own atlas plus our overlay (no game art is shipped)
"""
import os, pkgutil, shutil, struct, subprocess, sys, zlib

SAVE_KEY = b"TpeczKQL07HVdPbVUhAr6FjUsmRctyc5"
REMOTE_DIR = os.path.join("SmartSteamEmu", "210550", "remote")
STATE_FILE = "ap_state.lua"
IN_FILE = "ap_in.lua"
BACKUP_DIR = "ap_backup"
LOGO_SPRITE = b"MAIN_MENU_LOGO_NON_HD"
ICON_SPRITE = b"ICON_ARCHIPELAGO"
ATLAS = os.path.join("data", "images", "pc", "MENU_ELEMENTS_1")
REPLACED = [os.path.join("data", "scripts", "gamelogic.lua"), ATLAS + ".png", ATLAS + ".dat"]
HELPER_LNK = "ap_helper.lnk"  # opened by the game (ShellExecute) to start the hidden client
LAUNCHER_EXE = "Angry Birds Space Archipelago.exe"  # opens the game-styled launcher directly
ADDED = [os.path.join("data", "scripts", "gamelogic_orig.lua"), os.path.join("data", "scripts", "ap.lua"), HELPER_LNK,
         LAUNCHER_EXE]

# ---------------------------------------------------------------- AES-256 decrypt (CBC)
_SBOX = bytes.fromhex(
    "637c777bf26b6fc53001672bfed7ab76ca82c97dfa5947f0add4a2af9ca472c0b7fd9326363ff7cc34a5e5f171d8311504c723c31896"
    "059a071280e2eb27b27509832c1a1b6e5aa0523bd6b329e32f8453d100ed20fcb15b6acbbe394a4c58cfd0efaafb434d338545f9027f"
    "503c9fa851a3408f929d38f5bcb6da2110fff3d2cd0c13ec5f974417c4a77e3d645d197360814fdc222a908846eeb814de5e0bdbe032"
    "3a0a4906245cc2d3ac629195e479e7c8376d8dd54ea96c56f4ea657aae08ba78252e1ca6b4c6e8dd741f4bbd8b8a703eb5664803f60e"
    "613557b986c11d9ee1f8981169d98e949b1e87e9ce5528df8ca1890dbfe6426841992d0fb054bb16")
_INV = bytes(_SBOX.index(i) for i in range(256))


def _mul(a, b):
    r = 0
    while b:
        if b & 1:
            r ^= a
        a = ((a << 1) ^ 0x11B) if a & 0x80 else a << 1
        b >>= 1
    return r


_M9, _M11, _M13, _M14 = ([_mul(i, m) for i in range(256)] for m in (9, 11, 13, 14))


def _round_keys(key):
    nk, rounds = len(key) // 4, len(key) // 4 + 6
    w = [list(key[4 * i:4 * i + 4]) for i in range(nk)]
    rcon = 1
    for i in range(nk, 4 * (rounds + 1)):
        t = list(w[-1])
        if i % nk == 0:
            t = [_SBOX[b] for b in t[1:] + t[:1]]
            t[0] ^= rcon
            rcon = _mul(rcon, 2)
        elif nk > 6 and i % nk == 4:
            t = [_SBOX[b] for b in t]
        w.append([a ^ b for a, b in zip(w[i - nk], t)])
    return [sum(w[4 * r:4 * r + 4], []) for r in range(rounds + 1)]


def _decrypt_block(rk, block):
    s = [a ^ b for a, b in zip(block, rk[-1])]
    for r in range(len(rk) - 2, -1, -1):
        s = [s[((c - r_) % 4) * 4 + r_] for c in range(4) for r_ in range(4)]  # InvShiftRows (column-major)
        s = [_INV[b] for b in s]
        s = [a ^ b for a, b in zip(s, rk[r])]
        if r:
            n = []
            for c in range(4):
                a0, a1, a2, a3 = s[4 * c:4 * c + 4]
                n += [_M14[a0] ^ _M11[a1] ^ _M13[a2] ^ _M9[a3], _M9[a0] ^ _M14[a1] ^ _M11[a2] ^ _M13[a3],
                      _M13[a0] ^ _M9[a1] ^ _M14[a2] ^ _M11[a3], _M11[a0] ^ _M13[a1] ^ _M9[a2] ^ _M14[a3]]
            s = n
    return bytes(s)


def decrypt_save(raw: bytes) -> str:
    rk, prev, out = _round_keys(SAVE_KEY), bytes(16), bytearray()
    for i in range(0, len(raw) - len(raw) % 16, 16):
        blk = raw[i:i + 16]
        out += bytes(a ^ b for a, b in zip(_decrypt_block(rk, blk), prev))
        prev = blk
    return out.rstrip(b"\n").decode("latin1")


# ---------------------------------------------------------------- minimal PNG (RGBA8, non-interlaced)
def png_read(data, progress=None):
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    p, idat = 8, b""
    while p < len(data):
        n, tag = struct.unpack(">I4s", data[p:p + 8])
        body = data[p + 8:p + 8 + n]
        if tag == b"IHDR":
            w, h, depth, ctype, _, _, inter = struct.unpack(">IIBBBBB", body)
            assert (depth, ctype, inter) == (8, 6, 0), "only RGBA8 non-interlaced PNGs are supported"
        elif tag == b"IDAT":
            idat += body
        p += 12 + n
    raw, stride, rows, prev = zlib.decompress(idat), w * 4, [], bytearray(w * 4)
    for y in range(h):
        if progress and y % 32 == 0:
            progress(y / h)
        f, line = raw[y * (stride + 1)], bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for x in range(stride):
            a = line[x - 4] if x >= 4 else 0
            b = prev[x]
            c = prev[x - 4] if x >= 4 else 0
            if f == 1: line[x] = (line[x] + a) & 255
            elif f == 2: line[x] = (line[x] + b) & 255
            elif f == 3: line[x] = (line[x] + (a + b) // 2) & 255
            elif f == 4:
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        rows.append(line)
        prev = line
    return w, h, rows


def png_write(w, h, rows):
    def chunk(tag, body):
        return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF)
    raw = zlib.compress(b"".join(b"\0" + bytes(r) for r in rows), 9)
    # the game's PNG loader hangs on one huge IDAT; split it like libpng does
    idat = b"".join(chunk(b"IDAT", raw[i:i + 8192]) for i in range(0, len(raw), 8192))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + idat + chunk(b"IEND", b""))


def _over(dst, src):
    """src-over-dst for one RGBA pixel (lists of 4 ints)."""
    sa, da = src[3] / 255, dst[3] / 255
    oa = sa + da * (1 - sa)
    if oa == 0:
        return [0, 0, 0, 0]
    return [round((src[i] * sa + dst[i] * da * (1 - sa)) / oa) for i in range(3)] + [round(oa * 255)]


def add_sprite(dat, name, x, y, w, h, px, py):
    """Append a sprite entry to a KA3D/SPRT .dat and fix its counts and sizes."""
    dat = bytearray(dat)
    p = 18 + 2 + struct.unpack_from(">H", dat, 18)[0]  # past the image file name
    struct.pack_into(">H", dat, p, struct.unpack_from(">H", dat, p)[0] + 1)
    dat += struct.pack(">H", len(name)) + name + struct.pack(">4H2h", x, y, w, h, px, py)
    struct.pack_into(">I", dat, 4, len(dat) - 8)
    struct.pack_into(">I", dat, 12, len(dat) - 16)
    return bytes(dat)


def build_logo_atlas(atlas_png, atlas_dat, overlay_png, icon_png, progress=None):
    """Return (png, dat) bytes: the atlas grown downward with the logo + overlay (rect repointed)
    and the Archipelago menu icon (new sprite ICON_ARCHIPELAGO)."""
    report = progress or (lambda f: None)
    aw, ah, arows = png_read(atlas_png, lambda f: report(0.75 * f))  # decoding the atlas is most of the work
    ow, oh, orows = png_read(overlay_png)
    iw, ih, irows = png_read(icon_png)
    dat = bytearray(atlas_dat)
    off = dat.index(struct.pack(">H", len(LOGO_SPRITE)) + LOGO_SPRITE) + 2 + len(LOGO_SPRITE)
    x, y, w, h, px, py = struct.unpack_from(">4H2h", dat, off)
    assert ow == w and oh >= h, "overlay does not match this game's logo sprite"
    new = [bytearray(r) for r in orows]
    report(0.78)
    for j in range(h):  # original logo drawn on top of the overlay
        src, dst = arows[y + j], new[j]
        for i in range(w):
            s = list(src[4 * (x + i):4 * (x + i) + 4])
            if s[3]:
                dst[4 * i:4 * i + 4] = bytes(_over(list(dst[4 * i:4 * i + 4]), s))
    ny = ah + 1
    rows = arows + [bytearray(aw * 4)]
    for r in new:
        line = bytearray(aw * 4)
        line[4 * x:4 * (x + w)] = r
        rows.append(line)
    rows.append(bytearray(aw * 4))
    iy = len(rows)
    for r in irows:
        line = bytearray(aw * 4)
        line[0:iw * 4] = r
        rows.append(line)
    rows.append(bytearray(aw * 4))
    struct.pack_into(">4H2h", dat, off, x, ny, w, oh, px, py)
    dat = add_sprite(dat, ICON_SPRITE, 0, iy, iw, ih, iw // 2, ih // 2)
    report(0.85)
    png = png_write(aw, len(rows), rows)
    report(1.0)
    return png, dat


# ---------------------------------------------------------------- install / uninstall
def _pkg(name):
    return pkgutil.get_data(__name__.rsplit(".", 1)[0], "mod/" + name)


def is_installed(game_dir):
    p = os.path.join(game_dir, "data", "scripts", "ap.lua")
    return (os.path.exists(p) and open(p, "rb").read() == _pkg("ap.lua")
            and os.path.exists(os.path.join(game_dir, HELPER_LNK))
            and os.path.exists(os.path.join(game_dir, LAUNCHER_EXE)))


def install(game_dir, launcher=None, progress=None):
    """progress(fraction, step text) is called along the way when given (the launcher's progress bar)."""
    step = progress or (lambda f, text: None)
    if not os.path.exists(os.path.join(game_dir, "AngryBirdsSpace.exe")):
        raise FileNotFoundError(f"AngryBirdsSpace.exe not found in {game_dir}")
    step(0.0, "Backing up the original game files")
    backup = os.path.join(game_dir, BACKUP_DIR)
    for rel in REPLACED:  # the backup is taken once and never overwritten
        dst = os.path.join(backup, rel)
        if not os.path.exists(dst):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(os.path.join(game_dir, rel), dst)
    step(0.05, "Installing the Archipelago scripts")
    scripts = os.path.join(game_dir, "data", "scripts")
    shutil.copy2(os.path.join(backup, REPLACED[0]), os.path.join(scripts, "gamelogic_orig.lua"))
    for f in ("gamelogic.lua", "ap.lua"):
        open(os.path.join(scripts, f), "wb").write(_pkg(f))
    step(0.1, "Painting the Archipelago title screen")
    png, dat = build_logo_atlas(open(os.path.join(backup, ATLAS + ".png"), "rb").read(),
                                open(os.path.join(backup, ATLAS + ".dat"), "rb").read(), _pkg("logo_overlay.png"),
                                _pkg("ap_menu_icon.png"), lambda f: step(0.1 + 0.75 * f, "Painting the Archipelago title screen"))
    open(os.path.join(game_dir, ATLAS + ".png"), "wb").write(png)
    open(os.path.join(game_dir, ATLAS + ".dat"), "wb").write(dat)
    step(0.87, "Setting up the in-game connection")
    make_helper_shortcut(game_dir, launcher)
    step(0.97, "Adding the launcher")
    exe = os.path.join(game_dir, LAUNCHER_EXE)
    try:
        open(exe, "wb").write(_pkg("AngryBirdsSpaceArchipelago.exe"))
    except PermissionError:
        pass  # the exe is running (it started this install); the copy there is fine
    step(1.0, "Done!")


def make_helper_shortcut(game_dir, launcher=None):
    """Shortcut the game opens to start this client headless (no console: the launcher is a GUI exe)."""
    if launcher or getattr(sys, "frozen", False):
        target, args = launcher or sys.executable, '"Angry Birds Space Client" -- --helper'
    else:
        import Utils
        target = sys.executable
        args = f'"{os.path.join(Utils.local_path(), "Launcher.py")}" "Angry Birds Space Client" -- --helper'
    lnk = os.path.join(game_dir, HELPER_LNK)
    q = lambda v: "'" + v.replace("'", "''") + "'"
    script = (f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut({q(lnk)});"
              f"$s.TargetPath={q(target)};$s.Arguments={q(args)};"
              f"$s.WorkingDirectory={q(os.path.dirname(target))};$s.WindowStyle=7;$s.Save()")
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], check=True,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=60)


def uninstall(game_dir):
    backup = os.path.join(game_dir, BACKUP_DIR)
    for rel in REPLACED:
        shutil.copy2(os.path.join(backup, rel), os.path.join(game_dir, rel))
    for rel in ADDED + [IN_FILE, "ap_status.lua"]:
        p = os.path.join(game_dir, rel)
        if os.path.exists(p):
            os.remove(p)


# ---------------------------------------------------------------- Lua text helpers
def lua_str(s):
    """Quote a string for Lua; non-ASCII is dropped because the game's fonts are ASCII-only."""
    s = "".join(c if 32 <= ord(c) < 127 else "?" for c in str(s))
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def lua_value(v, indent=""):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return lua_str(v)
    if isinstance(v, dict):
        inner = indent + "  "
        return "{\n" + "".join(f"{inner}[{lua_str(k)}] = {lua_value(x, inner)},\n" for k, x in v.items()) + indent + "}"
    if isinstance(v, (list, tuple)):
        inner = indent + "  "
        return "{\n" + "".join(f"{inner}{lua_value(x, inner)},\n" for x in v) + indent + "}"
    raise TypeError(type(v))


# ---------------------------------------------------------------- save profiles
# A profile is a folder of the game's save files (the .lua files in the Steam cloud folder).
# Switching moves the current saves into the active profile's folder and the chosen profile's in.
PROFILES_DIR = "ap_profiles"
DEFAULT_PROFILE = "Default"


def _profiles_root(game_dir):
    return os.path.join(game_dir, PROFILES_DIR)


def active_profile(game_dir):
    p = os.path.join(_profiles_root(game_dir), "active.txt")
    return open(p, encoding="utf-8").read().strip() if os.path.exists(p) else DEFAULT_PROFILE


def list_profiles(game_dir):
    root = _profiles_root(game_dir)
    names = sorted(d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d))) if os.path.isdir(root) else []
    active = active_profile(game_dir)
    return sorted(set(names) | {active}, key=str.lower), active


def _save_files(folder):
    return [f for f in os.listdir(folder) if f.lower().endswith(".lua")] if os.path.isdir(folder) else []


def _valid_name(name):
    name = name.strip()
    if not name or len(name) > 24 or any(c in name for c in '\\/:*?"<>|.') or name.lower() == "active.txt":
        raise ValueError("Use 1-24 letters, numbers or spaces")
    return name


def new_profile(game_dir, name):
    name = _valid_name(name)
    path = os.path.join(_profiles_root(game_dir), name)
    if os.path.exists(path) or name == active_profile(game_dir):
        raise ValueError(f"'{name}' already exists")
    os.makedirs(path)  # empty: the game starts fresh in this profile
    return name


def switch_profile(game_dir, name):
    """Stash the current saves under the active profile and bring in `name`'s. Game must be closed."""
    if game_running():
        raise RuntimeError("Close the game first")
    active = active_profile(game_dir)
    if name == active:
        return
    remote = os.path.join(game_dir, REMOTE_DIR)
    root = _profiles_root(game_dir)
    target = os.path.join(root, name)
    if not os.path.isdir(target):
        raise ValueError(f"No profile '{name}'")
    stash = os.path.join(root, active)
    os.makedirs(stash, exist_ok=True)
    os.makedirs(remote, exist_ok=True)
    for f in _save_files(stash):  # replace the stash with what is live now
        os.remove(os.path.join(stash, f))
    for f in _save_files(remote):
        shutil.move(os.path.join(remote, f), os.path.join(stash, f))
    for f in _save_files(target):
        shutil.copy2(os.path.join(target, f), os.path.join(remote, f))
    open(os.path.join(root, "active.txt"), "w", encoding="utf-8").write(name)


def delete_profile(game_dir, name):
    if name == active_profile(game_dir):
        raise ValueError("Switch to another profile before deleting this one")
    path = os.path.join(_profiles_root(game_dir), name)
    if os.path.isdir(path):
        shutil.rmtree(path)


def game_running():
    import ctypes
    from ctypes import wintypes

    class PE(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_void_p), ("th32ModuleID", wintypes.DWORD),
                    ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260)]
    k = ctypes.windll.kernel32
    k.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    snap = k.CreateToolhelp32Snapshot(2, 0)
    e = PE()
    e.dwSize = ctypes.sizeof(PE)
    found, ok = False, k.Process32FirstW(snap, ctypes.byref(e))
    while ok:
        if e.szExeFile.lower() == "angrybirdsspace.exe":
            found = True
            break
        ok = k.Process32NextW(snap, ctypes.byref(e))
    k.CloseHandle(snap)
    return found


def start_game(game_dir):
    """Start the game the way its folder expects (Steam emulator loader if present)."""
    for exe in ("SmartSteamLoader.exe", "AngryBirdsSpace.exe"):
        p = os.path.join(game_dir, exe)
        if os.path.exists(p):
            subprocess.Popen([p], cwd=game_dir)
            return
    raise FileNotFoundError("AngryBirdsSpace.exe not found")
