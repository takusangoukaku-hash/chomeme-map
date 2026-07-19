# -*- coding: utf-8 -*-
"""指定した動画IDのメタデータ(概要欄・投稿日など)を data/meta/{id}.json に保存する。

usage: python fetch_meta.py <id> [<id> ...]
       python fetch_meta.py --title-hits   # タイトルに「ちょめめ」を含む動画すべて
"""
import json
import random
import sys
import time
from pathlib import Path

import yt_dlp

DATA = Path(__file__).resolve().parent.parent / "data"
MDIR = DATA / "meta"
MDIR.mkdir(exist_ok=True)


def target_ids(argv):
    if "--title-hits" in argv:
        videos = json.loads((DATA / "videos.json").read_text(encoding="utf-8"))
        ids = [v["id"] for v in videos
               if v["title"] and ("ちょめめ" in v["title"] or "チョメメ" in v["title"])]
        extra = [a for a in argv if a != "--title-hits"]
        return ids + extra
    return argv


def main():
    ids = target_ids(sys.argv[1:])
    opts = {"quiet": True, "no_warnings": True, "skip_download": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        for vid in ids:
            out = MDIR / f"{vid}.json"
            if out.exists():
                print(f"skip {vid}")
                continue
            try:
                info = ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False)
            except Exception as e:
                print(f"ERROR {vid}: {e}")
                continue
            meta = {
                "id": vid,
                "title": info.get("title"),
                "upload_date": info.get("upload_date"),
                "description": info.get("description"),
                "duration": info.get("duration"),
                "view_count": info.get("view_count"),
            }
            out.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"OK {vid} {meta['title'][:40]}")
            time.sleep(2 + random.uniform(0, 2))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
