# ちょめめマップ

SUSURU TV.(すするTV)が「ちょめめ」(=超美味い)と発言したラーメン店を地図にまとめるプロジェクト。

- **公開URL**: https://takusangoukaku-hash.github.io/chomeme-map/ (GitHub Pages, main:/docs)
- **PWA**: スマホでホーム画面に追加するとアプリとして起動できる。sw.jsのVERSIONとindex.htmlの?v=NNを揃えて更新すること
- **自動更新**: 毎日21:30に **Windowsタスクスケジューラ**のタスク `chomeme-map-daily-update` が
  `pythonw scripts/run_update.py`(画面を出さず scripts/update.py を実行、ログは data/update.log)を起動し、
  新着動画の判定→shops.json更新→git push(Pagesが自動再デプロイ)。PCが21:30に起動していなければ次回起動時に自動で追いつく
  (StartWhenAvailable)。実行結果は data/last_run.json、未通知の新着店舗は data/pending_notify.json に残る
- **通知**: Claudeのスケジュールタスク(同名)は実行そのものは行わず、`scripts/wait_update.py` で更新の完了を待って
  新着店舗をプッシュ通知するだけ。もし21:30の更新がまだ始まっていなければ保険としてタスクスケジューラを起動する。
  Claudeアプリが閉じていて通知タスクが動かなかった日の新着は pending_notify.json に溜まり、次に動いた日にまとめて通知される

## データソース(3系統)

1. **タイトル**: 【ちょめめ】付き動画(約20本)→ 概要欄「【本日のお店】」から店名・住所
2. **総集編**: 年間ちょめめ総集編(2022/2023/2024)のチャプター → 公式のちょめめ店リスト
3. **文字起こし**: 全動画(約4100本)の自動字幕から「ちょめ」系パターンを検索し、
   候補箇所の音声をWhisperで再文字起こしして検証(自動字幕は「ちょめめ」を
   「ちょめ」「ちょめえ」等に誤認識するため2段構え)

## パイプライン

```
scripts/fetch_videos.py       チャンネル全動画リスト → data/videos.json
scripts/fetch_transcripts.py  全動画の日本語自動字幕 → data/transcripts/{id}.json
                              (YouTubeのIP制限が厳しいため15秒間隔+ブロック時15分待機。丸1日級)
scripts/search_chomeme.py     字幕から「ちょめめ」候補を検索 → data/hits.json
scripts/verify_whisper.py     候補箇所の音声をWhisperで検証 → data/verified.json
scripts/fetch_meta.py         動画の概要欄取得 → data/meta/{id}.json
scripts/extract_shops.py      店舗情報抽出 → data/shops_raw.json
scripts/build_shops.py        マージ+ジオコーディング(国土地理院API) → site/shops.json
```

## サイト

`site/index.html` — Leaflet + OpenStreetMap の静的サイト。
ピンをクリックすると店名・サムネイル・動画リンク(ちょめめ発言シーンへのタイムスタンプ付き)。

## 注意

- YouTube字幕エンドポイントはIP単位で厳しくレート制限される(15リクエスト程度でブロック)。
  fetch_transcripts.py は再開可能なので、止まっても再実行すればよい
- ジオコーディング結果は data/geocode_cache.json にキャッシュされる

## おまけ: 星3.5マップ(`docs/tabelog/`, `scripts/tabelog/`)

食べログの評価3.5以上の店を地図に出し、現在地から近い順・ジャンル別に探す**個人用**アプリ。

- **データは公開しない**: 食べログ由来のデータ(`data/tabelog/`)は .gitignore 済みで、
  Pages にも載らない。公開されるのはデータの無いアプリの画面だけ
- **使い方**
  1. `scripts/tabelog/areas.txt` で取得エリアを選ぶ(初期は新宿・渋谷のみ)
  2. PCで `python scripts/tabelog/scrape.py` → `data/tabelog/tabemap.json` ができる
     (初回は店ごとに座標を取るので1エリア数十分。2回目以降は一覧の再取得だけで数分)
  3. `tabemap.json` をスマホに送り(Googleドライブ等)、
     https://takusangoukaku-hash.github.io/chomeme-map/tabelog/ の「データ読込」で選ぶ。
     データは端末の localStorage にだけ保存される
- 取得は1リクエスト3〜5秒間隔。403/429 が返ったら即停止するので、半日以上空けて再実行
- 店が1件も読めない時は食べログのHTMLが変わった可能性。`--debug` で HTML を
  `data/tabelog/debug/` に保存して `scrape.py` の正規表現を直す
- 食べログの利用規約は自動収集を禁止している。取得頻度を上げない・結果を他人に渡さないこと
