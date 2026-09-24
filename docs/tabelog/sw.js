// 星3.5マップ Service Worker
// キャッシュ名は tabemap-* 。ちょめめマップ(chomeme-*)のキャッシュには触らない。
// 画面はネットワーク優先(更新がすぐ反映される)、オフライン時だけキャッシュを使う。
const VERSION = "v1";  // v1: 初版
const CACHE = `tabemap-${VERSION}`;
const SHELL = [
  "./",
  "./manifest.json",
  "./icon-192.png",
  "https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css",
  "https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js",
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) => Promise.all(
      keys.filter((k) => k.startsWith("tabemap-") && k !== CACHE).map((k) => caches.delete(k))
    )).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET") return;
  // 地図タイル・フォントはキャッシュしない(容量対策)
  if (url.hostname === "tiles.openfreemap.org" || url.hostname === "maps.gsi.go.jp") return;

  if (e.request.mode === "navigate") {
    e.respondWith(
      fetch(e.request).then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put("./", copy));
        return res;
      }).catch(() => caches.match("./"))
    );
    return;
  }
  e.respondWith(caches.match(e.request).then((hit) => hit || fetch(e.request)));
});
