# -*- coding: utf-8 -*-
"""動画の日本語字幕(自動生成含む)を取得して data/transcripts/{id}.json に保存する。
再開可能: 既に保存済み・取得不可記録済みの動画はスキップする。

usage: python fetch_transcripts.py [--limit N] [--delay SEC]
"""
import argparse
import json
import random
import sys
import time
from pathlib import Path

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable,
    IpBlocked,
    RequestBlocked,
)

DATA = Path(__file__).resolve().parent.parent / "data"
TDIR = DATA / "transcripts"
FAILED = DATA / "failed.json"


def load_failed():
    if FAILED.exists():
        return json.loads(FAILED.read_text(encoding="utf-8"))
    return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="今回処理する最大本数")
    ap.add_argument("--delay", type=float, default=15.0, help="リクエスト間の待機秒")
    ap.add_argument("--block-wait", type=float, default=900.0, help="IPブロック検知時の待機秒")
    ap.add_argument("--max-blocks", type=int, default=20, help="ブロック待機の最大回数(超えたら終了)")
    args = ap.parse_args()

    videos = json.loads((DATA / "videos.json").read_text(encoding="utf-8"))
    failed = load_failed()
    api = YouTubeTranscriptApi()

    done = 0
    blocks = 0
    queue = [v for v in videos if not (TDIR / f"{v['id']}.json").exists() and v["id"] not in failed]
    print(f"remaining: {len(queue)}")
    i = 0
    while i < len(queue):
        if args.limit is not None and done >= args.limit:
            break
        v = queue[i]
        vid = v["id"]
        out = TDIR / f"{vid}.json"
        try:
            fetched = api.fetch(vid, languages=["ja"])
            segs = [
                {"t": round(s.start, 1), "d": round(s.duration, 1), "text": s.text}
                for s in fetched
            ]
            out.write_text(json.dumps(segs, ensure_ascii=False), encoding="utf-8")
            print(f"OK   {vid} ({len(segs)} segs) {v['title'][:40]}", flush=True)
        except (TranscriptsDisabled, NoTranscriptFound, VideoUnavailable) as e:
            failed[vid] = type(e).__name__
            FAILED.write_text(json.dumps(failed, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"SKIP {vid} {type(e).__name__}", flush=True)
        except (IpBlocked, RequestBlocked):
            blocks += 1
            if blocks > args.max_blocks:
                # IPブロックは想定内。今日の分はここまでとして正常終了する
                # (異常終了にすると呼び出し側のパイプラインが止まってしまう)
                print("too many blocks, ending this run normally", flush=True)
                break
            print(f"BLOCKED (#{blocks}) waiting {args.block_wait}s ...", flush=True)
            time.sleep(args.block_wait)
            api = YouTubeTranscriptApi()
            continue  # 同じ動画をリトライ
        except Exception as e:
            # 想定外のエラーも1本スキップして続行(1本の不具合で全体を止めない)
            print(f"ERROR {vid} {type(e).__name__}: {e}", flush=True)
            failed[vid] = type(e).__name__
            FAILED.write_text(json.dumps(failed, ensure_ascii=False, indent=1), encoding="utf-8")
        i += 1
        done += 1
        time.sleep(args.delay + random.uniform(0, args.delay * 0.5))

    total = len(list(TDIR.glob("*.json")))
    remaining = len(videos) - total - len(failed)
    print(f"done this run: {done}, total transcripts: {total}, "
          f"failed: {len(failed)}, remaining: {remaining}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
