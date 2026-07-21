# -*- coding: utf-8 -*-
"""毎日の増分更新パイプライン。

1. チャンネルの最新動画をチェックして videos.json に追記
2. 新着動画のメタデータ・字幕を取得
3. ちょめめ判定(タイトル + 字幕候補検索 + Whisper音声検証)
4. shops.json を再ビルド
5. 変更があれば git commit & push (--no-push で抑止)

最後に集計を1行のJSON(サマリ行 SUMMARY: {...})で出力する。
"""
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
DATA = ROOT / "data"
DOCS = ROOT / "docs"

sys.path.insert(0, str(SCRIPTS))


def run(script, *args, check=True):
    r = subprocess.run([sys.executable, str(SCRIPTS / script), *args],
                       capture_output=True, text=True, encoding="utf-8")
    print(f"--- {script} {' '.join(args)} (exit {r.returncode})")
    if r.stdout:
        print(r.stdout[-2000:])
    if r.returncode != 0:
        print(r.stderr[-2000:] if r.stderr else "")
        if check:
            raise RuntimeError(f"{script} failed")
    return r


def fetch_recent_videos(n=30):
    """最新n本を取得して videos.json にマージ。新規IDリストを返す"""
    import yt_dlp
    opts = {
        "extract_flat": True, "quiet": True, "no_warnings": True,
        "playlist_items": f"1-{n}",
        "extractor_args": {"youtube": {"lang": ["ja"]}, "youtubetab": {"lang": ["ja"]}},
        "http_headers": {"Accept-Language": "ja-JP,ja;q=0.9"},
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info("https://www.youtube.com/@susurutv/videos", download=False)
    latest = [{"id": e["id"], "title": e.get("title"),
               "duration": e.get("duration"), "view_count": e.get("view_count")}
              for e in info.get("entries", []) if e]

    vfile = DATA / "videos.json"
    videos = json.loads(vfile.read_text(encoding="utf-8"))
    known = {v["id"] for v in videos}
    new = [v for v in latest if v["id"] not in known]
    if new:
        videos = new + videos
        vfile.write_text(json.dumps(videos, ensure_ascii=False, indent=1), encoding="utf-8")
    return new


def fetch_new_transcripts(ids):
    """新着動画の字幕を取得(少数なのでブロックリスクは低い)。
    新しい動画はまだ自動字幕が生成されていないことがあるため、
    失敗しても failed.json に永続化せず次回リトライさせる"""
    from youtube_transcript_api import YouTubeTranscriptApi
    api = YouTubeTranscriptApi()
    got = []
    for vid in ids:
        out = DATA / "transcripts" / f"{vid}.json"
        if out.exists():
            got.append(vid)
            continue
        try:
            fetched = api.fetch(vid, languages=["ja"])
            segs = [{"t": round(s.start, 1), "d": round(s.duration, 1), "text": s.text}
                    for s in fetched]
            out.write_text(json.dumps(segs, ensure_ascii=False), encoding="utf-8")
            got.append(vid)
            print(f"transcript OK {vid}")
        except Exception as e:
            print(f"transcript pending {vid}: {type(e).__name__}")
        time.sleep(5)
    return got


def git(*args):
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print(f"git {' '.join(args)} failed: {r.stderr}")
    return r


def shop_names(payload):
    shops = payload if isinstance(payload, list) else payload.get("shops", [])
    return {s["name"] for s in shops}


def argval(name, default):
    """--name VALUE 形式の引数を読む"""
    if name in sys.argv:
        i = sys.argv.index(name)
        if i + 1 < len(sys.argv):
            return int(sys.argv[i + 1])
    return default


def main():
    push = "--no-push" not in sys.argv
    # 1回の実行で消化する字幕の本数と、IPブロック待機の許容回数
    backfill = argval("--backfill", 200)
    max_blocks = argval("--max-blocks", 8)

    before = json.loads((DOCS / "shops.json").read_text(encoding="utf-8"))

    new_videos = fetch_recent_videos()
    print(f"new videos: {[v['id'] for v in new_videos]}")

    # 新着動画のメタデータ(タイトルちょめめ判定と店舗情報の両方に使う)
    if new_videos:
        run("fetch_meta.py", *[v["id"] for v in new_videos], check=False)
        fetch_new_transcripts([v["id"] for v in new_videos])

    # 直近3日以内に「字幕なし」で失敗記録された動画は記録を消して再試行対象に戻す
    ffile = DATA / "failed.json"
    if ffile.exists():
        failed = json.loads(ffile.read_text(encoding="utf-8"))
        videos = json.loads((DATA / "videos.json").read_text(encoding="utf-8"))
        recent_ids = {v["id"] for v in videos[:10]}
        pruned = {k: v for k, v in failed.items() if k not in recent_ids}
        if pruned != failed:
            ffile.write_text(json.dumps(pruned, ensure_ascii=False, indent=1), encoding="utf-8")

    # 字幕バックログの消化(全4000本超は長期戦。IPブロックしたらその日は打ち切り)
    if backfill > 0:
        run("fetch_transcripts.py", "--limit", str(backfill),
            "--delay", "15", "--max-blocks", str(max_blocks), check=False)

    # ここから先は途中で失敗しても最後のビルド＋コミットまで必ず到達させる
    # (1ステップの失敗で更新が丸ごと止まると、進捗が見えなくなるため)
    try:
        run("search_chomeme.py", check=False)
        run("verify_whisper.py", "--hits", check=False)

        # 検証済みヒットの動画メタが無ければ取得(build_shopsが店舗情報に使う)
        vfile = DATA / "verified.json"
        if vfile.exists():
            need = [r["id"] for r in json.loads(vfile.read_text(encoding="utf-8"))
                    if r.get("verified") and not (DATA / "meta" / f"{r['id']}.json").exists()]
            if need:
                run("fetch_meta.py", *sorted(set(need)), check=False)

        run("fetch_meta.py", "--title-hits", check=False)
        run("extract_shops.py", check=False)
        nm = DATA / "need_meta.json"
        if nm.exists():
            ids = json.loads(nm.read_text(encoding="utf-8"))
            if ids:
                run("fetch_meta.py", *ids, check=False)
                run("extract_shops.py", check=False)
    except Exception as e:
        print(f"gathering phase error (continuing to build): {type(e).__name__}: {e}")

    run("build_shops.py")

    after = json.loads((DOCS / "shops.json").read_text(encoding="utf-8"))
    new_shops = sorted(shop_names(after) - shop_names(before))

    changed = git("status", "--porcelain").stdout.strip() != ""
    if changed and push:
        git("add", "-A")
        git("commit", "-m", f"auto-update {time.strftime('%Y-%m-%d')}"
            + (f": 新規 {', '.join(new_shops)}" if new_shops else ""))
        git("push")

    summary = {
        "new_videos": [v["title"] for v in new_videos],
        "new_shops": new_shops,
        "total_shops": len(shop_names(after)),
        "progress": after.get("progress"),
        "pushed": changed and push,
    }
    print("SUMMARY: " + json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
