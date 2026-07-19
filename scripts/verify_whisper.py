# -*- coding: utf-8 -*-
"""字幕検索で見つかった候補箇所の音声を切り出してWhisperで再文字起こしし、
「ちょめめ」発言かどうかを検証する。

usage: python verify_whisper.py <videoid> <sec> [<videoid> <sec> ...]
       python verify_whisper.py --hits   # data/hits.json の全候補を検証 → data/verified.json
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
CLIP = 12  # 前後に切り出す秒数

_model = None


def model():
    global _model
    if _model is None:
        # faster-whisper(CTranslate2)はこの端末のアプリ制御ポリシーでDLLが
        # ブロックされるため、PyTorch版whisperを使う
        import whisper
        _model = whisper.load_model("small")
    return _model


def download_clip(vid: str, t: float, dest: Path) -> Path:
    start, end = max(0, t - CLIP), t + CLIP
    out = dest / f"{vid}_{int(t)}.m4a"
    if out.exists():
        return out
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "-f", "bestaudio[ext=m4a]/bestaudio",
        "--download-sections", f"*{start}-{end}",
        "-o", str(out),
        "--quiet", "--no-warnings",
        f"https://www.youtube.com/watch?v={vid}",
    ]
    subprocess.run(cmd, check=True, timeout=300)
    return out


def transcribe(path: Path) -> str:
    result = model().transcribe(
        str(path),
        language="ja",
        initial_prompt="ちょめめ!超美味い。ちょめめです。",
        fp16=False,
    )
    return result["text"]


def verify_one(vid: str, t: float, workdir: Path):
    try:
        clip = download_clip(vid, t, workdir)
        text = transcribe(clip)
        hit = "ちょめ" in text or "チョメ" in text
        return {"id": vid, "t": t, "whisper": text, "verified": hit}
    except Exception as e:
        return {"id": vid, "t": t, "error": f"{type(e).__name__}: {e}"}


def main():
    work = DATA / "clips"
    work.mkdir(exist_ok=True)
    vfile = DATA / "verified.json"
    results = json.loads(vfile.read_text(encoding="utf-8")) if vfile.exists() else []
    done = {(r["id"], r["t"]) for r in results if "error" not in r}

    if "--hits" in sys.argv:
        hits = json.loads((DATA / "hits.json").read_text(encoding="utf-8"))
        pairs = [(h["id"], m["t"]) for h in hits for m in h["matches"]]
    else:
        args = sys.argv[1:]
        pairs = [(args[i], float(args[i + 1])) for i in range(0, len(args), 2)]

    new = 0
    for vid, t in pairs:
        if (vid, t) in done:
            continue
        r = verify_one(vid, t, work)
        results = [x for x in results if not (x["id"] == vid and x["t"] == t)]
        results.append(r)
        new += 1
        print(json.dumps(r, ensure_ascii=False), flush=True)
        vfile.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")

    ok = sum(1 for r in results if r.get("verified"))
    print(f"newly checked: {new}, verified total: {ok}/{len(results)}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
