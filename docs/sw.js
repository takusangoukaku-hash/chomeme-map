// ちょめめマップ Service Worker
// バージョン更新時は VERSION と index.html の ?v=NN を揃えて上げること
const VERSION = "v4";
const SHELL_CACHE = `chomeme-shell-${VERSION}`;
const DATA_CACHE = "chomeme-data";

const SHELL = [
  "./",
  `./index.html?v=4`,
  "./manifest.json",
  "./icon-192.png",
  "https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css",
  "https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js",
];

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(SHELL_CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.filter((k) => k.startsWith("chomeme-shell-") && k !== SHELL_CACHE)
            .map((k) => caches.delete(k))
      )
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);

  // データはネットワーク優先(オフライン時のみキャッシュ)
  if (url.pathname.endsWith("/shops.json")) {
    e.respondWith(
      fetch(e.request)
        .then((res) => {
          const copy = res.clone();
          caches.open(DATA_CACHE).then((c) => c.put(e.request, copy));
          return res;
        })
        .catch(() => caches.match(e.request))
    );
    return;
  }

  // 地図のベクトルタイル・フォント・サムネはキャッシュしない(容量対策)
  if (url.hostname === "tiles.openfreemap.org" ||
      url.hostname === "maps.gsi.go.jp" ||
      url.hostname === "img.youtube.com") {
    return;
  }

  // シェルはキャッシュ優先
  e.respondWith(
    caches.match(e.request, { ignoreSearch: false }).then((hit) => hit || fetch(e.request))
  );
});
