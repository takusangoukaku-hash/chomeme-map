# -*- coding: utf-8 -*-
"""星3.5マップのPWAアイコンを生成する(濃紺地にゴールドの星+「3.5」)"""
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parents[2] / "docs" / "tabelog"
BG = (28, 36, 58)
GOLD = (242, 180, 45)
WHITE = (255, 255, 255)


def star(cx, cy, r_out, r_in):
    pts = []
    for i in range(10):
        r = r_out if i % 2 == 0 else r_in
        a = -math.pi / 2 + i * math.pi / 5
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def make(size: int, maskable: bool) -> Image.Image:
    img = Image.new("RGB", (size, size), BG)
    d = ImageDraw.Draw(img)
    s = size / 512 * (0.8 if maskable else 1.0)  # maskableは安全領域に収める
    c = size / 2
    d.polygon(star(c, c - 40 * s, 150 * s, 62 * s), fill=GOLD)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", int(120 * s))
    except OSError:
        font = ImageFont.load_default()
    d.text((c, c + 165 * s), "3.5", fill=WHITE, font=font, anchor="mm")
    return img


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    make(192, False).save(OUT / "icon-192.png")
    make(512, False).save(OUT / "icon-512.png")
    make(512, True).save(OUT / "icon-512-maskable.png")
    print("icons ->", OUT)
