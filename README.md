# ちょめめマップ

SUSURU TV.(すするTV)が「ちょめめ」(=超美味い)と発言したラーメン店を地図にまとめるプロジェクト。

- **公開URL**: https://takusangoukaku-hash.github.io/chomeme-map/ (GitHub Pages, main:/docs)
- **PWA**: スマホでホーム画面に追加するとアプリとして起動できる。sw.jsのVERSIONとindex.htmlの?v=NNを揃えて更新すること
- **自動更新**: 毎日21:30にスケジュールタスク(chomeme-map-daily-update)が scripts/update.py を実行し、
  新着動画の判定→shops.json更新→git push(Pagesが自動再デプロイ)。新着店舗があればプッシュ通知が届く

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
