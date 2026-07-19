# -*- coding: utf-8 -*-
"""data/meta/*.json から店舗情報を抽出する。

- 個別動画: 概要欄の「【本日のお店】」ブロック → 店名・住所・食べログURL
- 総集編: チャプター行「M:SS 店名(都道府県)」→ 店名と都道府県。
  videos.json のタイトルから元動画を推定し、未取得なら meta 取得候補として出力

出力: data/shops_raw.json, 追加で取得すべき動画ID一覧を data/need_meta.json に
"""
import json
import re
import sys
import unicodedata
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"

CHAPTER_RE = re.compile(r"^(\d+(?::\d+){1,2})\s*(.+?)(?:（(.+?)）)?\s*$")
COMPILATION_IDS = {"dlO5YEG3xvI", "2X9PDKgZU5E", "sYFgFC-3BPE"}


def ts_to_sec(ts: str) -> int:
    parts = [int(p) for p in ts.split(":")]
    sec = 0
    for p in parts:
        sec = sec * 60 + p
    return sec


def parse_shop_block(desc: str):
    """【本日のお店】ブロックから (店名, 住所, 食べログURL) を返す"""
    m = re.search(r"【本日の(?:お店|ラーメン情報)】\s*\n(.*?)(?:\n\s*\n|★|☆|▼|■)", desc, re.S)
    if not m:
        return None
    lines = [l.strip() for l in m.group(1).splitlines() if l.strip()]
    name = lines[0] if lines else None
    address = None
    tabelog = None
    for l in lines[1:]:
        um = re.search(r"https?://\S+", l)
        if um and "tabelog" in um.group(0) and tabelog is None:
            tabelog = um.group(0)
        l = re.sub(r"https?://\S+", "", l).strip()
        if l and re.match(r".+?[都道府県]", l) and address is None:
            address = l
    return {"name": name, "address": address, "tabelog": tabelog}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    return re.sub(r"[\s・]", "", s).lower()


def names_compatible(a: str, b: str) -> bool:
    na, nb = norm(a), norm(b)
    return bool(na and nb) and (na in nb or nb in na)


def main():
    videos = json.loads((DATA / "videos.json").read_text(encoding="utf-8"))
    shops = []
    need_meta = set()
    have_meta = {p.stem for p in (DATA / "meta").glob("*.json")}

    for p in sorted((DATA / "meta").glob("*.json")):
        meta = json.loads(p.read_text(encoding="utf-8"))
        vid = meta["id"]
        desc = meta.get("description") or ""

        if vid in COMPILATION_IDS:
            year = re.search(r"(20\d\d)", meta["title"])
            for line in desc.splitlines():
                m = CHAPTER_RE.match(line.strip())
                if not m:
                    continue
                ts, name, pref = m.groups()
                shop = {
                    "name": name.strip(),
                    "pref": pref,
                    "source": "compilation",
                    "comp_id": vid,
                    "comp_t": ts_to_sec(ts),
                    "comp_year": year.group(1) if year else None,
                }
                # 元動画をタイトルから推定し、概要欄の店名と照合して確定する
                key = norm(name)
                cands = [v for v in videos
                         if v["id"] not in COMPILATION_IDS and key and key in norm(v["title"])]
                validated = None
                unfetched = []
                for v in cands[:6]:
                    mp = DATA / "meta" / f"{v['id']}.json"
                    if not mp.exists():
                        unfetched.append(v["id"])
                        continue
                    vm = json.loads(mp.read_text(encoding="utf-8"))
                    info = parse_shop_block(vm.get("description") or "")
                    if info and info.get("name") and names_compatible(name, info["name"]):
                        validated = v
                        break
                if validated:
                    shop["orig_id"] = validated["id"]
                    shop["orig_title"] = validated["title"]
                else:
                    # 検証できる meta がまだない候補を取得対象に積む
                    need_meta.update(unfetched[:2])
                shops.append(shop)
        else:
            # metaは総集編の元動画解決や新着チェック用にも取得されるため、
            # タイトルに「ちょめめ」がある動画だけを個別ソースとして採用する
            # (文字起こし検出分は verified.json 経由で build_shops が反映する)
            title = meta.get("title") or ""
            if "ちょめめ" not in title and "チョメメ" not in title:
                continue
            info = parse_shop_block(desc)
            if info:
                shops.append({
                    **info,
                    "source": "title",
                    "video_id": vid,
                    "video_title": meta["title"],
                    "upload_date": meta.get("upload_date"),
                })
            else:
                print(f"WARN no shop block: {vid} {meta['title'][:40]}")

    (DATA / "shops_raw.json").write_text(
        json.dumps(shops, ensure_ascii=False, indent=1), encoding="utf-8")
    (DATA / "need_meta.json").write_text(
        json.dumps(sorted(need_meta), ensure_ascii=False, indent=1), encoding="utf-8")
    matched = sum(1 for s in shops if s.get("orig_id"))
    comp = sum(1 for s in shops if s["source"] == "compilation")
    print(f"shops: {len(shops)} (compilation: {comp}, matched to orig: {matched}), need_meta: {len(need_meta)}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
