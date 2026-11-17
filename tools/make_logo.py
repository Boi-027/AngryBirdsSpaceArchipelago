"""Builds the 'Angry Birds Space / Archipelago' title logo from the game's own art.

'ARCHIPELAGO' is typeset with the game's FONT_SPACE_BIG_HEADLINE glyphs (the same green,
dark-outlined style as 'SPACE') and placed under the original logo. The atlas grows downward
and the MAIN_MENU_LOGO_NON_HD rect is pointed at the new, taller logo.

usage: make_logo.py <original images/pc dir> <fonts/1024x768 dir> <out dir>
"""
import struct, sys, os
from PIL import Image

SPRITE = b"MAIN_MENU_LOGO_NON_HD"
TEXT = "ARCHIPELAGO"
OVERLAP = 4      # glyphs include their outline; overlap neighbours slightly like the game does
SCALE = 1.0      # native glyph size: no resampling keeps the letters crisp
TILT = 0         # no rotation, also for crispness
AP_ICON = r"C:\ProgramData\Archipelago\data\icon.png"
OUTLINE = (24, 40, 16, 255)  # dark outline matching the headline font


def load_pvr(path):
    """PVR v2, RGBA4444 only (all the Space fonts use it)."""
    b = open(path, "rb").read()
    hl, h, w, _mips, flags = struct.unpack_from("<5I", b, 0)
    assert flags & 0xFF == 0x10, "expected RGBA4444 PVR"
    d = b[hl:hl + w * h * 2]
    px = bytearray(w * h * 4)
    for i in range(w * h):
        v = d[2 * i] | d[2 * i + 1] << 8
        px[4 * i:4 * i + 4] = bytes(((v >> s) & 15) * 17 for s in (12, 8, 4, 0))
    return Image.frombytes("RGBA", (w, h), bytes(px))


def load_font(font_dir, name="FONT_SPACE_BIG_HEADLINE"):
    sheet = load_pvr(os.path.join(font_dir, name + ".pvr"))
    b = open(os.path.join(font_dir, name + ".dat"), "rb").read()
    n = struct.unpack_from(">H", b, 0x12)[0]
    p = 0x14 + n
    _line_h, count = struct.unpack_from(">HI", b, p)
    glyphs = {}
    for i in range(count):
        ch, x, y, w, h, base = struct.unpack_from(">6h", b, p + 6 + 12 * i)
        glyphs[chr(ch)] = (sheet.crop((x, y, x + w, y + h)), base)
    return glyphs


def typeset(glyphs, text):
    parts = []
    for i, ch in enumerate(text):
        im, base = glyphs[ch]
        if TILT:
            im = im.rotate(TILT if i % 2 else -TILT, resample=Image.BICUBIC, expand=True)
        parts.append((im, base + (im.height - glyphs[ch][0].height) // 2))
    asc = max(b for _, b in parts)
    h = max(asc - b + im.height for im, b in parts)
    w = sum(im.width - OVERLAP for im, _ in parts) + OVERLAP
    out = Image.new("RGBA", (w, h))
    x = 0
    for im, b in parts:
        out.alpha_composite(im, (x, asc - b))
        x += im.width - OVERLAP
    out = out.crop(out.getbbox())
    if SCALE == 1.0:
        return out
    return out.resize((round(out.width * SCALE), round(out.height * SCALE)), Image.LANCZOS)


def ap_icon(size):
    """Archipelago icon with a game-style dark outline."""
    from PIL import ImageFilter
    from PIL import ImageEnhance
    icon = Image.open(AP_ICON).convert("RGBA").resize((size - 6, size - 6), Image.LANCZOS)
    icon = ImageEnhance.Color(icon).enhance(1.6)  # match the game's saturated palette
    out = Image.new("RGBA", (size, size))
    a = Image.new("L", (size, size))
    a.paste(icon.getchannel("A"), (3, 3))
    ring = Image.new("RGBA", (size, size), OUTLINE)
    ring.putalpha(a.filter(ImageFilter.MaxFilter(5)))
    out.alpha_composite(ring)
    out.alpha_composite(icon, (3, 3))
    return out


def menu_icon(size=(56, 54), outline=(8, 58, 0, 255)):
    """AP logo as a main-menu button icon in the game's style: white circles, dark green outlines."""
    from PIL import ImageChops, ImageFilter
    w, h = size
    d = min(w, h) - 6
    src = Image.open(AP_ICON).convert("RGBA").resize((d * 4, d * 4), Image.LANCZOS)
    # lines where two differently coloured circles meet, found at 4x then scaled down
    rgb = src.convert("RGB")
    edge = Image.new("L", rgb.size)
    for dx, dy in ((1, 0), (0, 1)):
        diff = ImageChops.difference(rgb, ImageChops.offset(rgb, dx, dy)).convert("L")
        edge = ImageChops.lighter(edge, diff.point(lambda v: 255 if v > 40 else 0))
    a = src.getchannel("A").point(lambda v: 255 if v > 128 else 0)
    edge = ImageChops.multiply(edge, a.filter(ImageFilter.MinFilter(3))).filter(ImageFilter.MaxFilter(9))
    a, edge = a.resize((d, d), Image.LANCZOS), edge.resize((d, d), Image.LANCZOS)
    off = ((w - d) // 2, (h - d) // 2)
    mask, lines = Image.new("L", size), Image.new("L", size)
    mask.paste(a, off)
    lines.paste(edge, off)
    out = Image.new("RGBA", size, outline)
    out.putalpha(mask.filter(ImageFilter.MaxFilter(5)))
    white = Image.new("RGBA", size, (255, 255, 255, 255))
    white.putalpha(ImageChops.subtract(mask, lines))
    out.alpha_composite(white)
    return out


def app_icon(size=256):
    """Launcher exe / window icon (our own drawing, in the game's style): green round button with the AP flower."""
    from PIL import ImageDraw, ImageFilter
    n = size * 4  # supersample, then scale down
    im = Image.new("RGBA", (n, n))
    d = ImageDraw.Draw(im)
    d.ellipse((0, 0, n - 1, n - 1), fill=(255, 255, 255, 255))                 # white rim
    d.ellipse((n * 0.06, n * 0.06, n * 0.94, n * 0.94), fill=(20, 70, 10, 255))  # dark ring
    grad = Image.new("RGBA", (1, n))
    for y in range(n):                                                         # green, lighter at the top
        t = y / (n - 1)
        grad.putpixel((0, y), (int(196 - 110 * t), int(232 - 90 * t), int(40 - 30 * t), 255))
    mask = Image.new("L", (n, n))
    ImageDraw.Draw(mask).ellipse((n * 0.09, n * 0.09, n * 0.91, n * 0.91), fill=255)
    body = Image.new("RGBA", (n, n))
    body.paste(grad.resize((n, n)), (0, 0), mask)
    im.alpha_composite(body)
    shine = Image.new("L", (n, n))
    ImageDraw.Draw(shine).ellipse((n * 0.22, n * 0.13, n * 0.78, n * 0.42), fill=60)
    glow = Image.new("RGBA", (n, n), (255, 255, 255, 0))
    glow.putalpha(shine.filter(ImageFilter.GaussianBlur(n * 0.03)))
    im.alpha_composite(glow)
    flower = menu_icon((int(n * 0.62), int(n * 0.6)))
    im.alpha_composite(flower, ((n - flower.width) // 2, (n - flower.height) // 2 + int(n * 0.02)))
    return im.resize((size, size), Image.LANCZOS)


def find_rect(dat, name):
    i = dat.index(struct.pack(">H", len(name)) + name) + 2 + len(name)
    return i, struct.unpack_from(">4H2h", dat, i)


def main(img_dir, font_dir, out_dir):
    atlas = Image.open(os.path.join(img_dir, "MENU_ELEMENTS_1.png")).convert("RGBA")
    dat = bytearray(open(os.path.join(img_dir, "MENU_ELEMENTS_1.dat"), "rb").read())
    off, (x, y, w, h, px, py) = find_rect(dat, SPRITE)
    logo = atlas.crop((x, y, x + w, y + h))

    text = typeset(load_font(font_dir), TEXT)
    icon = ap_icon(text.height + 6)
    gap = 4
    word = Image.new("RGBA", (icon.width + gap + text.width, icon.height))
    word.alpha_composite(icon, (0, 0))
    word.alpha_composite(text, (icon.width + gap, (icon.height - text.height) // 2))
    assert word.width <= w, "ARCHIPELAGO line wider than the logo"
    tuck = 2  # sit just under 'SPACE'
    nh = h - tuck + word.height
    new = Image.new("RGBA", (w, nh))
    new.alpha_composite(word, ((w - word.width) // 2, h - tuck))
    overlay = new.copy()  # our part only; the client composites the player's own logo on top
    new.alpha_composite(logo, (0, 0))  # original logo stays on top

    ny = atlas.height + 1
    grown = Image.new("RGBA", (atlas.width, ny + nh + 1))
    grown.alpha_composite(atlas, (0, 0))
    grown.alpha_composite(new, (x, ny))
    struct.pack_into(">4H2h", dat, off, x, ny, w, nh, px, py)
    assert find_rect(bytes(dat), SPRITE)[1][:4] == (x, ny, w, nh)

    os.makedirs(out_dir, exist_ok=True)
    grown.save(os.path.join(out_dir, "MENU_ELEMENTS_1.png"))
    open(os.path.join(out_dir, "MENU_ELEMENTS_1.dat"), "wb").write(dat)
    new.save(os.path.join(out_dir, "logo_preview.png"))
    overlay.save(os.path.join(out_dir, "logo_overlay.png"))
    menu_icon().save(os.path.join(out_dir, "ap_menu_icon.png"))
    icon = app_icon(256)
    icon.save(os.path.join(out_dir, "ap_launcher_icon.png"))
    icon.save(os.path.join(out_dir, "ap_launcher_icon.ico"), sizes=[(256, 256), (64, 64), (48, 48), (32, 32), (16, 16)])


if __name__ == "__main__":
    main(*sys.argv[1:4])
