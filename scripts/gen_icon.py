# -*- coding: utf-8 -*-
"""PWAアイコンを生成する(赤地に白文字「ちょめめ」+ 丼の縁取り)"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

DOCS = Path(__file__).resolve().parent.parent / "docs"
RED = (200, 56, 46)
WHITE = (255, 255, 255)


def make(size: int, maskable: bool) -> Image.Image:
    img = Image.new("RGB", (size, size), RED)
    d = ImageDraw.Draw(img)
    s = size / 512  # 512基準でスケール

    # 丼(シンプルな椀+湯気)
    bowl_cx, bowl_cy = 256 * s, 210 * s
    bowl_w, bowl_h = 300 * s, 150 * s
    d.pieslice(
        [bowl_cx - bowl_w / 2, bowl_cy - bowl_h / 2,
         bowl_cx + bowl_w / 2, bowl_cy + bowl_h * 1.2],
        0, 180, fill=WHITE)
    d.rectangle([bowl_cx - bowl_w / 2, bowl_cy - 8 * s,
                 bowl_cx + bowl_w / 2, bowl_cy + 8 * s], fill=WHITE)
    # 麺(赤い波線の代わりに縦線)
    for i in range(-3, 4):
        x = bowl_cx + i * 34 * s
        d.line([x, bowl_cy - 60 * s, x, bowl_cy - 5 * s], fill=WHITE, width=int(10 * s))

    # 文字「ちょめめ」
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/YuGothB.ttc", int(96 * s))
    except OSError:
        font = ImageFont.truetype("C:/Windows/Fonts/msgothic.ttc", int(96 * s))
    text = "ちょめめ"
    bbox = d.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    d.text((256 * s - tw / 2, 350 * s), text, font=font, fill=WHITE)

    if maskable:
        # セーフゾーン確保のため80%に縮小して中央配置
        inner = img.resize((int(size * 0.8), int(size * 0.8)), Image.LANCZOS)
        img = Image.new("RGB", (size, size), RED)
        off = (size - inner.width) // 2
        img.paste(inner, (off, off))
    return img


def main():
    make(192, False).save(DOCS / "icon-192.png")
    make(512, False).save(DOCS / "icon-512.png")
    make(512, True).save(DOCS / "icon-512-maskable.png")
    print("icons saved")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
