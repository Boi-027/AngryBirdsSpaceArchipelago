"""Self-check for worlds/angrybirdsspace/gamefiles.py against the reference libraries (dev machine only)."""
import os, sys, io, random
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "worlds", "angrybirdsspace"))
sys.path.insert(0, HERE)
import gamefiles, abcrypt
from PIL import Image

# AES: random texts through the reference encryptor, decrypted by the pure-Python one
for n in (1, 15, 16, 17, 100, 5000):
    text = bytes(random.choice(b"abc xyz={}\"'\n,0123") for _ in range(n)).strip(b"\n") or b"a"
    assert gamefiles.decrypt_save(abcrypt.encrypt_save(text)) == text.decode(), n

# PNG: decode a real filtered PNG (written by PIL) and compare pixels
im = Image.effect_noise((37, 23), 64).convert("RGBA")
buf = io.BytesIO(); im.save(buf, "PNG", optimize=True)
w, h, rows = gamefiles.png_read(buf.getvalue())
assert (w, h) == im.size and b"".join(rows) == im.tobytes()
w2, h2, rows2 = gamefiles.png_read(gamefiles.png_write(w, h, rows))
assert b"".join(rows2) == im.tobytes()

def _parse_dat(b):
    import struct
    p = 18; n = struct.unpack_from(">H", b, p)[0]; p += 2 + n
    cnt = struct.unpack_from(">H", b, p)[0]; p += 2
    out = []
    for _ in range(cnt):
        n = struct.unpack_from(">H", b, p)[0]; name = b[p + 2:p + 2 + n].decode(); p += 2 + n
        out.append((name,) + struct.unpack_from(">4H2h", b, p)); p += 12
    assert p == len(b)
    return out


# Logo: rebuilt atlas must match the PIL-built one in the logo area
mod = os.path.join(HERE, "..")
a = os.path.join(mod, "backup", "data", "images", "pc", "MENU_ELEMENTS_1")
ov = os.path.join(mod, "worlds", "angrybirdsspace", "mod", "logo_overlay.png")
if os.path.exists(ov):
    icon = os.path.join(mod, "worlds", "angrybirdsspace", "mod", "ap_menu_icon.png")
    png, dat = gamefiles.build_logo_atlas(open(a + ".png", "rb").read(), open(a + ".dat", "rb").read(),
                                          open(ov, "rb").read(), open(icon, "rb").read())
    ref = Image.open(os.path.join(mod, "build", "images", "MENU_ELEMENTS_1.png")).convert("RGBA")
    got = Image.open(io.BytesIO(png)).convert("RGBA")
    # the logo area must match the PIL-built reference
    region = (0, 0, ref.width, ref.height)
    g, r = got.crop(region).tobytes(), ref.tobytes()
    assert max(abs(p - q) for p, q in zip(g, r)) <= 2
    # the icon sprite is registered and its pixels are where the .dat says
    sys.path.insert(0, HERE)
    entries = dict((e[0], e[1:]) for e in _parse_dat(dat))
    x, y, w, h, px, py = entries["ICON_ARCHIPELAGO"]
    assert got.crop((x, y, x + w, y + h)).tobytes() == Image.open(icon).convert("RGBA").tobytes()
    assert len(dat) - 8 == int.from_bytes(dat[4:8], "big")
print("gamefiles ok")
