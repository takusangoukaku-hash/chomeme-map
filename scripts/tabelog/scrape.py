# -*- coding: utf-8 -*-
"""食べログの評価3.5以上の店を集めて、星3.5マップ用の JSON を作る(個人利用専用)。

使い方:
    python scripts/tabelog/scrape.py                 # areas.txt の全エリアを取得
    python scripts/tabelog/scrape.py tokyo/A1304     # エリアを指定して取得
    python scripts/tabelog/scrape.py --min 3.6       # 下限を変える(既定 3.5)
    python scripts/tabelog/scrape.py --debug         # 取得したHTMLを data/tabelog/debug/ に保存

出力:
    data/tabelog/cache.json    店ごとのキャッシュ(座標は一度取れば再取得しない)
    data/tabelog/tabemap.json  アプリに読み込ませるファイル(スマホへ送って「データ読込」)

注意:
- 食べログの利用規約は自動収集を禁止している。個人の手元で使う範囲に留め、
  結果(data/tabelog/ 以下)を公開リポジトリや GitHub Pages に置かないこと。
  data/tabelog/ は .gitignore 済み(update.py の git add -A でも上がらない)。
- 相手サーバーに負荷をかけないよう 1リクエストごとに数秒待つ。間隔は縮めないこと。
  403/429 が返ったら即座に止まる。
"""
import argparse
import gzip
import html
import json
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data" / "tabelog"
CACHE = OUT_DIR / "cache.json"
OUTPUT = OUT_DIR / "tabemap.json"
DEBUG_DIR = OUT_DIR / "debug"
AREAS_FILE = Path(__file__).resolve().parent / "areas.txt"

BASE = "https://tabelog.com"
MAX_PAGES = 60          # 食べログの一覧は60ページ(1200件)までしか辿れない
WAIT = (3.0, 5.0)       # リクエスト間隔(秒)。縮めないこと
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")

DEBUG = False
_last_request = 0.0


class Blocked(Exception):
    pass


def fetch(url: str) -> str:
    """間隔を空けて GET する。403/429 は Blocked で即中断。"""
    global _last_request
    wait = random.uniform(*WAIT) - (time.time() - _last_request)
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept-Language": "ja,en;q=0.5",
        "Accept-Encoding": "gzip",
    })
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                body = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    body = gzip.decompress(body)
                _last_request = time.time()
                return body.decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            _last_request = time.time()
            if e.code in (403, 429):
                raise Blocked(f"HTTP {e.code}: {url}")
            if e.code == 404:
                return ""
            if attempt == 2:
                raise
        except urllib.error.URLError:
            _last_request = time.time()
            if attempt == 2:
                raise
        time.sleep(10 * (attempt + 1))
    return ""


def save_debug(name: str, text: str):
    if DEBUG:
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        (DEBUG_DIR / name).write_text(text, encoding="utf-8")


def strip_tags(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


# ---------- 一覧ページ ----------

NAME_A = re.compile(r"<a\b[^>]*list-rst__rst-name-target[^>]*>(.*?)</a>", re.S)
HREF = re.compile(r'href="([^"]+)"')
SHOP_URL = re.compile(r"^https://tabelog\.com/(\w+)/A\d{4}/A\d{6}/(\d+)/?$")
RATING = re.compile(r'list-rst__rating-val[^>]*>\s*([\d.]+)\s*<')
AREA_GENRE = re.compile(r'list-rst__area-genre[^>]*>(.*?)</', re.S)
BUDGET = re.compile(r"(?:￥[\d,]+\s*～\s*￥[\d,]+|￥[\d,]+\s*～|～\s*￥[\d,]+)")


def parse_list(page: str) -> list:
    """一覧ページから店(URL・名前・評価・最寄り・ジャンル・予算)を抜き出す。"""
    items = []
    tags = list(NAME_A.finditer(page))
    for i, m in enumerate(tags):
        href = HREF.search(m.group(0))
        if not href:
            continue
        url = href.group(1).split("?")[0]
        if not url.endswith("/"):
            url += "/"
        um = SHOP_URL.match(url)
        if not um:
            continue
        # この店の名前タグから次の店の名前タグまでが、この店の情報
        seg = page[m.end(): tags[i + 1].start() if i + 1 < len(tags) else len(page)]
        rm = RATING.search(seg)
        rating = float(rm.group(1)) if rm else None
        station, genre = "", ""
        am = AREA_GENRE.search(seg)
        if am:
            text = strip_tags(am.group(1))
            if " / " in text:
                station, genre = text.rsplit(" / ", 1)
            else:
                genre = text
            station = re.sub(r"^\[[^\]]*\]\s*", "", station)  # 先頭の [東京] を除く
        budgets = [re.sub(r"\s+", "", b) for b in BUDGET.findall(strip_tags(seg))]
        items.append({
            "id": um.group(2),
            "url": url,
            "name": strip_tags(m.group(1)),
            "rating": rating,
            "station": station,
            "genre": genre,
            "dinner": budgets[0] if len(budgets) > 0 else "",
            "lunch": budgets[1] if len(budgets) > 1 else "",
        })
    return items


def list_url(area: str, page: int) -> str:
    """area 例: 'tokyo/A1304'  'tokyo/A1304/A130401'  'tokyo/A1304/rstLst/ramen' """
    area = area.strip("/")
    if "/rstLst" in area:
        head, genre = area.split("/rstLst", 1)
        genre = genre.strip("/")
    else:
        head, genre = area, ""
    path = f"/{head}/rstLst/" + (f"{genre}/" if genre else "") + (f"{page}/" if page > 1 else "")
    return BASE + path + "?SrtT=rt"  # 評価の高い順


def crawl_area(area: str, min_rating: float) -> list:
    found = []
    for page in range(1, MAX_PAGES + 1):
        url = list_url(area, page)
        text = fetch(url)
        save_debug(f"list_{area.replace('/', '_')}_{page}.html", text)
        items = parse_list(text)
        if not items:
            if page == 1:
                print(f"  ! 店が1件も読めませんでした: {url}\n"
                      f"    (エリア指定の誤りか、食べログのHTMLが変わった可能性。--debug で保存して確認)")
            break
        rated = [it for it in items if it["rating"] is not None]
        hits = [it for it in rated if it["rating"] >= min_rating]
        found.extend(hits)
        print(f"  p{page}: {len(items)}件中 {len(hits)}件が{min_rating}以上 (最低 {min((it['rating'] for it in rated), default=0):.2f})")
        # 評価順なので、下限を下回った店が出たらそれ以降は見なくてよい
        if len(hits) < len(rated) or len(items) < 20:
            break
    else:
        print(f"  ! {MAX_PAGES}ページ目まで全部{min_rating}以上でした。取りこぼしがあるので"
              f" areas.txt でこのエリアを小エリア(例 {area}/A130401)に分けてください")
    return found


# ---------- 店舗ページ(座標) ----------

LD_JSON = re.compile(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', re.S)
MAP_LATLNG = [
    re.compile(r"center=(-?\d+\.\d+),(-?\d+\.\d+)"),
    re.compile(r"markers=[^\"'&]*?(?:%7C|\|)(-?\d+\.\d+),(-?\d+\.\d+)"),
    re.compile(r'"latitude"\s*:\s*"?(-?\d+\.\d+)"?\s*,\s*"longitude"\s*:\s*"?(-?\d+\.\d+)'),
]
ADDRESS = re.compile(r'rstinfo-table__address[^>]*>(.*?)</p>', re.S)


def _walk_ld(obj):
    if isinstance(obj, list):
        for o in obj:
            yield from _walk_ld(o)
    elif isinstance(obj, dict):
        yield obj
        for k in ("@graph",):
            if k in obj:
                yield from _walk_ld(obj[k])


def parse_detail(page: str) -> dict:
    """店舗ページから座標と住所を取る。JSON-LD → 地図画像のURL → 住所の順に試す。"""
    out = {"lat": None, "lng": None, "address": ""}
    for m in LD_JSON.finditer(page):
        try:
            data = json.loads(html.unescape(m.group(1)))
        except ValueError:
            continue
        for o in _walk_ld(data):
            geo = o.get("geo") or {}
            if geo.get("latitude") and out["lat"] is None:
                out["lat"], out["lng"] = float(geo["latitude"]), float(geo["longitude"])
            addr = o.get("address")
            if isinstance(addr, dict) and not out["address"]:
                out["address"] = "".join(str(addr.get(k, "")) for k in
                                         ("addressRegion", "addressLocality", "streetAddress"))
    if out["lat"] is None:
        for rx in MAP_LATLNG:
            m = rx.search(page)
            if m:
                out["lat"], out["lng"] = float(m.group(1)), float(m.group(2))
                break
    if not out["address"]:
        m = ADDRESS.search(page)
        if m:
            out["address"] = strip_tags(m.group(1))
    return out


def geocode_gsi(addr: str):
    """座標が取れなかった時だけ、住所を国土地理院APIで座標にする。"""
    q = urllib.parse.quote(re.sub(r"\s.*$", "", addr))
    try:
        req = urllib.request.Request(
            f"https://msearch.gsi.go.jp/address-search/AddressSearch?q={q}",
            headers={"User-Agent": "tabemap-personal/1.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            js = json.loads(r.read().decode("utf-8"))
        time.sleep(1.0)
        if js:
            lng, lat = js[0]["geometry"]["coordinates"]
            return lat, lng
    except Exception as e:
        print(f"    gsi error: {e}")
    return None


def fill_location(shop: dict):
    text = fetch(shop["url"])
    save_debug(f"rst_{shop['id']}.html", text)
    d = parse_detail(text)
    shop["address"] = d["address"] or shop.get("address", "")
    if d["lat"] is None and shop["address"]:
        ll = geocode_gsi(shop["address"])
        if ll:
            d["lat"], d["lng"] = ll
            shop["geo_by"] = "gsi"
    # 日本の範囲外は取り違えとみなして捨てる
    if d["lat"] is not None and 20 < d["lat"] < 46 and 122 < d["lng"] < 154:
        shop["lat"], shop["lng"] = round(d["lat"], 6), round(d["lng"], 6)


# ---------- メイン ----------

def load_areas(args_areas):
    if args_areas:
        return args_areas
    areas = []
    for line in AREAS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            areas.append(line)
    return areas


def main():
    global DEBUG
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("areas", nargs="*", help="例: tokyo/A1304 (省略時は areas.txt)")
    ap.add_argument("--min", type=float, default=3.5, help="評価の下限(既定 3.5)")
    ap.add_argument("--max-detail", type=int, default=0,
                    help="今回座標を取りに行く店の上限(0=無制限)。初回が長すぎる時に分割する用")
    ap.add_argument("--debug", action="store_true", help="取得したHTMLを保存する")
    args = ap.parse_args()
    DEBUG = args.debug

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    store = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    cache = store.setdefault("shops", {})
    crawled = store.setdefault("areas", {})  # エリア → 最後に一覧を最後まで見終えた時刻
    now = time.strftime("%Y-%m-%dT%H:%M:%S%z")

    def save():
        CACHE.write_text(json.dumps(store, ensure_ascii=False, indent=1), encoding="utf-8")

    areas = load_areas(args.areas)
    blocked = False
    try:
        # 1) 一覧から評価を更新(毎回)
        for area in areas:
            print(f"[一覧] {area}")
            for it in crawl_area(area, args.min):
                shop = cache.setdefault(it["id"], {})
                shop.update(it)
                shop["area"] = area
                shop["seen"] = now
            crawled[area] = now
            save()

        # 2) 座標がまだ無い店だけ店舗ページを見る(座標は変わらないので一度きり)
        todo = [s for s in cache.values() if s.get("lat") is None and not s.get("no_geo")]
        if args.max_detail:
            todo = todo[: args.max_detail]
        est = len(todo) * sum(WAIT) / 2 / 60
        print(f"[座標] {len(todo)}店 (目安 {est:.0f}分)")
        for i, shop in enumerate(todo, 1):
            fill_location(shop)
            if shop.get("lat") is None:
                shop["no_geo"] = True
                print(f"  ! 座標なし: {shop['name']} {shop['url']}")
            if i % 20 == 0 or i == len(todo):
                print(f"  {i}/{len(todo)}")
                save()
    except Blocked as e:
        blocked = True
        print(f"\n!! 食べログにブロックされました ({e})。ここで止めます。"
              f"\n   しばらく(半日〜1日)空けてから再実行してください。途中までの結果は保存済みです。")
    except KeyboardInterrupt:
        print("\n中断しました。途中までの結果は保存済みです。")
    finally:
        save()

    # 3) アプリ用ファイル。座標の無い店と、エリアの最新の一覧に載らなくなった店
    #    (評価が下限を割った・閉店)は出さない
    def current(s):
        return s.get("seen", "") >= crawled.get(s.get("area"), "")

    shops = [
        {k: s.get(k, "") for k in ("id", "name", "url", "rating", "genre", "station",
                                    "address", "lat", "lng", "dinner", "lunch")}
        for s in cache.values()
        if s.get("lat") is not None and (s.get("rating") or 0) >= args.min and current(s)
    ]
    shops.sort(key=lambda s: -s["rating"])
    OUTPUT.write_text(json.dumps({
        "format": "tabemap/1",
        "updated": now,
        "min": args.min,
        "shops": shops,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"\n→ {OUTPUT} ({len(shops)}店)")
    print("  このファイルをスマホに送り、アプリの「データ読込」から読み込んでください。")
    if blocked:
        sys.exit(2)


if __name__ == "__main__":
    main()
