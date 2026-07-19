# -*- coding: utf-8 -*-
"""保存済み字幕から「ちょめめ」発言(表記揺れ含む)を検索し data/hits.json に出力する"""
import json
import re
import sys
import unicodedata
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"

# 自動字幕の認識揺れを想定したパターン。
# 自動字幕は「ちょめめ」を「ちょめ」「ちょめえ」「おちょめ」等に崩すため、
# 「ちょめ」を含む箇所を広く候補にし、Whisper検証(verify_whisper.py)で絞る
PATTERN = re.compile(r"ちょ\s*め", re.IGNORECASE)


def norm(text: str) -> str:
    # カタカナ→ひらがな + NFKC正規化
    text = unicodedata.normalize("NFKC", text)
    return "".join(
        chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c
        for c in text
    )


def main():
    videos = {v["id"]: v for v in json.loads((DATA / "videos.json").read_text(encoding="utf-8"))}
    hits = []
    for f in sorted((DATA / "transcripts").glob("*.json")):
        vid = f.stem
        segs = json.loads(f.read_text(encoding="utf-8"))
        matches = []
        for i, s in enumerate(segs):
            if PATTERN.search(norm(s["text"])):
                ctx_before = segs[i - 1]["text"] if i > 0 else ""
                ctx_after = segs[i + 1]["text"] if i + 1 < len(segs) else ""
                matches.append({
                    "t": s["t"],
                    "text": s["text"],
                    "context": f"{ctx_before} / {s['text']} / {ctx_after}",
                })
        if matches:
            v = videos.get(vid, {})
            hits.append({
                "id": vid,
                "title": v.get("title"),
                "matches": matches,
            })
    (DATA / "hits.json").write_text(
        json.dumps(hits, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    n = sum(len(h["matches"]) for h in hits)
    print(f"videos with hits: {len(hits)}, total matches: {n}")
    for h in hits[:20]:
        print(f"- {h['id']} {h['title'][:50] if h['title'] else ''}")
        for m in h["matches"][:3]:
            print(f"    {m['t']}s: {m['text']}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
