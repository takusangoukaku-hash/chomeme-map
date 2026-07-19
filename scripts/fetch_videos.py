# -*- coding: utf-8 -*-
"""SUSURU TV. チャンネルの全動画リストを取得して data/videos.json に保存する"""
import json
import sys
from pathlib import Path

import yt_dlp

CHANNEL_URL = "https://www.youtube.com/@susurutv/videos"
OUT = Path(__file__).resolve().parent.parent / "data" / "videos.json"


def main():
    opts = {
        "extract_flat": True,
        "quiet": True,
        "no_warnings": True,
        # タイトルが視聴言語に自動翻訳されるのを防ぎ、原語(日本語)で取得する
        "extractor_args": {"youtube": {"lang": ["ja"]}, "youtubetab": {"lang": ["ja"]}},
        "http_headers": {"Accept-Language": "ja-JP,ja;q=0.9"},
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(CHANNEL_URL, download=False)

    videos = []
    for e in info.get("entries", []):
        if not e:
            continue
        videos.append({
            "id": e.get("id"),
            "title": e.get("title"),
            "duration": e.get("duration"),
            "view_count": e.get("view_count"),
        })

    OUT.write_text(json.dumps(videos, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"saved {len(videos)} videos -> {OUT}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
