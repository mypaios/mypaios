#!/usr/bin/env python3
"""Generate the PiAOS "π" brand icon (the 'Pi' mark, as in 3.14…).

Draws a rounded-square tile with a dark PiAOS gradient background and a
geometric π glyph in PiAOS Red — no font dependency, crisp at every size.
Outputs PWA icons, the Electron/Dock PNG, and a macOS .icns.

Brand: PiAOS Red #FF5758 · Dark Gray Blue #2E333D (palette.md).
"""
import os
import subprocess
from PIL import Image, ImageDraw

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RED = (255, 87, 88)          # PiAOS Red #FF5758
BG_TOP = (46, 51, 61)        # Dark Gray Blue #2E333D
BG_BOT = (20, 23, 29)        # darker foot of the gradient
SS = 4                       # supersample factor for smooth edges


def _rrect(draw, x0, y0, x1, y1, r, fill):
    draw.rounded_rectangle([x0, y0, x1, y1], radius=r, fill=fill)


def make_icon(size, bg=True):
    S = size * SS
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    if bg:
        # vertical gradient
        grad = Image.new("RGB", (1, S))
        for y in range(S):
            t = y / (S - 1)
            grad.putpixel((0, y), tuple(int(BG_TOP[i] + (BG_BOT[i] - BG_TOP[i]) * t) for i in range(3)))
        grad = grad.resize((S, S))
        mask = Image.new("L", (S, S), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=int(S * 0.225), fill=255)
        img.paste(grad, (0, 0), mask)

    d = ImageDraw.Draw(img)
    # π geometry as fractions of S (centered, optically balanced)
    # top bar
    _rrect(d, 0.15 * S, 0.30 * S, 0.85 * S, 0.405 * S, 0.0525 * S, RED)
    # left leg
    _rrect(d, 0.265 * S, 0.37 * S, 0.375 * S, 0.745 * S, 0.055 * S, RED)
    # right leg
    _rrect(d, 0.625 * S, 0.37 * S, 0.735 * S, 0.745 * S, 0.055 * S, RED)

    return img.resize((size, size), Image.LANCZOS)


def save(img, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.save(path)
    print("wrote", path.replace(REPO + "/", ""), img.size)


# 1) PWA icons (square tile, maskable-safe — π sits well inside the safe zone)
save(make_icon(192), os.path.join(REPO, "static", "icon-192.png"))
save(make_icon(512), os.path.join(REPO, "static", "icon-512.png"))

# 2) Electron / Dock master PNG
save(make_icon(1024), os.path.join(REPO, "desktop-electron", "assets", "icon.png"))

# 3) macOS .icns via iconutil
iconset = os.path.join(REPO, "desktop-electron", "assets", "icon.iconset")
os.makedirs(iconset, exist_ok=True)
for sz in (16, 32, 64, 128, 256, 512, 1024):
    make_icon(sz).save(os.path.join(iconset, f"icon_{sz}x{sz}.png"))
    if sz <= 512:
        make_icon(sz * 2).save(os.path.join(iconset, f"icon_{sz}x{sz}@2x.png"))
icns = os.path.join(REPO, "desktop-electron", "assets", "icon.icns")
subprocess.run(["iconutil", "-c", "icns", iconset, "-o", icns], check=True)
print("wrote", icns.replace(REPO + "/", ""))

# small favicon fallback PNG (some browsers prefer a raster)
save(make_icon(32), os.path.join(REPO, "static", "icon-32.png"))
print("DONE")
