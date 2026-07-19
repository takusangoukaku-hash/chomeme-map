# -*- coding: utf-8 -*-
"""shops_raw.json + meta から最終データ site/shops.json を生成する。

- 総集編由来の店は元動画の概要欄から住所を補完
- 同一店舗(正規化名が同じ)はマージ
- 住所を国土地理院APIでジオコーディング(失敗時はNominatim)。結果はキャッシュ
"""
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
SITE = Path(__file__).resolve().parent.parent / "docs"
CACHE = DATA / "geocode_cache.json"

from extract_shops import parse_shop_block, norm, names_compatible  # 再利用


def http_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "chomeme-map/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def clean_address(addr: str) -> str:
    """ビル名・階数などを落として番地までにする"""
    addr = unicodedata.normalize("NFKC", addr)
    addr = re.sub(r"\s+", " ", addr).strip()
    m = re.match(r"(.+?\d+(?:-\d+){0,3})", addr)
    return m.group(1) if m else addr


def geocode(addr: str, cache: dict):
    if addr in cache:
        return cache[addr]
    q = urllib.parse.quote(clean_address(addr))
    result = None
    try:
        js = http_json(f"https://msearch.gsi.go.jp/address-search/AddressSearch?q={q}")
        if js:
            lng, lat = js[0]["geometry"]["coordinates"]
            result = {"lat": lat, "lng": lng, "by": "gsi"}
    except Exception as e:
        print(f"  gsi error: {e}")
    if result is None:
        try:
            js = http_json(
                "https://nominatim.openstreetmap.org/search?format=json&limit=1&q="
                + urllib.parse.quote(addr))
            if js:
                result = {"lat": float(js[0]["lat"]), "lng": float(js[0]["lon"]), "by": "osm"}
        except Exception as e:
            print(f"  osm error: {e}")
    cache[addr] = result
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    time.sleep(1.1)
    return result


def load_verified_hits():
    """Whisper検証済みの「ちょめめ」発言箇所を [{id, t}] で返す"""
    vf = DATA / "verified.json"
    if not vf.exists():
        return []
    return [r for r in json.loads(vf.read_text(encoding="utf-8")) if r.get("verified")]


def main():
    shops_raw = json.loads((DATA / "shops_raw.json").read_text(encoding="utf-8"))
    metas = {p.stem: json.loads(p.read_text(encoding="utf-8"))
             for p in (DATA / "meta").glob("*.json")}
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}

    # 前回ビルドの added(初掲載日)を引き継ぐ
    prev_added = {}
    prev_file = SITE / "shops.json"
    if prev_file.exists():
        prev = json.loads(prev_file.read_text(encoding="utf-8"))
        prev_shops = prev if isinstance(prev, list) else prev.get("shops", [])
        for s in prev_shops:
            prev_added[norm(s["name"])] = s.get("added")

    # 表記が違いすぎて自動マージできない同一店舗の別名 (norm形で指定)
    aliases = {
        "japaneseramen五感": "ジャパニーズラーメン五感",
    }

    merged = {}  # norm(name) -> shop
    for s in shops_raw:
        name = (s.get("name") or "").lstrip("・").strip()
        if not name:
            continue
        key = aliases.get(norm(name), norm(name))
        m = merged.setdefault(key, {
            "name": name, "address": None, "tabelog": None, "videos": []})

        if s["source"] == "title":
            m["address"] = m["address"] or s.get("address")
            m["tabelog"] = m["tabelog"] or s.get("tabelog")
            m["videos"].append({
                "id": s["video_id"], "title": s["video_title"],
                "date": s.get("upload_date"), "source": "title", "t": None,
            })
        else:  # compilation
            orig = metas.get(s.get("orig_id") or "")
            if orig:
                info = parse_shop_block(orig.get("description") or "")
                if info:
                    m["address"] = m["address"] or info.get("address")
                    m["tabelog"] = m["tabelog"] or info.get("tabelog")
                if not any(v["id"] == orig["id"] for v in m["videos"]):
                    m["videos"].append({
                        "id": orig["id"], "title": orig["title"],
                        "date": orig.get("upload_date"), "source": "title", "t": None,
                    })
            m["videos"].append({
                "id": s["comp_id"],
                "title": f"ちょめめ総集編{s.get('comp_year') or ''}",
                "date": None, "source": "compilation", "t": s["comp_t"],
            })
            m["pref"] = s.get("pref")

    # Whisper検証済みの発言箇所を反映する。
    # 同じ動画が既にtitle由来で載っていればタイムスタンプ付きに格上げする
    for hit in load_verified_hits():
        meta = metas.get(hit["id"])
        if not meta:
            continue
        info = parse_shop_block(meta.get("description") or "")
        if not info or not info.get("name"):
            continue
        key = aliases.get(norm(info["name"]), norm(info["name"]))
        m = merged.setdefault(key, {
            "name": info["name"], "address": None, "tabelog": None, "videos": []})
        m["address"] = m["address"] or info.get("address")
        m["tabelog"] = m["tabelog"] or info.get("tabelog")
        existing = next((v for v in m["videos"] if v["id"] == hit["id"]), None)
        if existing:
            if existing.get("t") is None:
                existing["source"] = "transcript"
                existing["t"] = hit["t"]
        else:
            m["videos"].append({
                "id": hit["id"], "title": meta["title"],
                "date": meta.get("upload_date"), "source": "transcript", "t": hit["t"],
            })

    # 名前の包含関係+同一住所の店舗をマージ(「三浦家」と「ラーメン 三浦家」など)
    items = list(merged.values())
    absorbed = set()
    for i, a in enumerate(items):
        for j, b in enumerate(items):
            if i >= j or i in absorbed or j in absorbed:
                continue
            same_addr = a.get("address") and b.get("address") and \
                norm(a["address"])[:14] == norm(b["address"])[:14]
            if names_compatible(a["name"], b["name"]) and (same_addr or not a.get("address") or not b.get("address")):
                keep, drop = (a, b) if len(a["name"]) >= len(b["name"]) else (b, a)
                keep["address"] = keep.get("address") or drop.get("address")
                keep["tabelog"] = keep.get("tabelog") or drop.get("tabelog")
                keep["pref"] = keep.get("pref") or drop.get("pref")
                seen = {v["id"] for v in keep["videos"]}
                keep["videos"] += [v for v in drop["videos"]
                                   if v["id"] not in seen or v["source"] == "compilation"]
                absorbed.add(i if keep is b else j)
    items = [m for k, m in enumerate(items) if k not in absorbed]

    out = []
    for m in items:
        latlng = None
        if m.get("address"):
            print(f"geocoding: {m['name']} {m['address']}")
            latlng = geocode(m["address"], cache)
        elif m.get("pref"):
            print(f"no address, pref only: {m['name']} ({m['pref']})")
        m["lat"] = latlng["lat"] if latlng else None
        m["lng"] = latlng["lng"] if latlng else None
        m.pop("pref", None)
        k = norm(m["name"])
        # 前回ファイルに存在した店は added を引き継ぐ(未設定なら旧掲載扱い)。
        # 新規の店だけが今日の日付になり、NEW表示される
        m["added"] = prev_added.get(k) or ("20260101" if k in prev_added else time.strftime("%Y%m%d"))
        out.append(m)

    SITE.mkdir(exist_ok=True)
    payload = {
        "updated": time.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "shops": out,
    }
    (SITE / "shops.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    located = sum(1 for s in out if s["lat"] is not None)
    print(f"shops: {len(out)}, located: {located} -> {SITE / 'shops.json'}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
