/* Service worker : l'application s'ouvre sans connexion.
   - fichiers de l'application : servis depuis le cache, mis à jour en arrière-plan ;
   - data/snapshot.json : réseau d'abord (données fraîches), cache si hors ligne ;
   - requêtes vers d'autres sites (The Odds API) : jamais interceptées. */
const VERSION = "20261026-090330";
const CACHE = "valuebet-" + VERSION;
const SHELL = ["./", "index.html", "local-api.js", "manifest.webmanifest", "icons/icon-192.png", "icons/icon-512.png", "data/snapshot.json"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((ks) => Promise.all(ks.filter((k) => k.startsWith("valuebet-") && k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request, url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== location.origin) return;
  if (url.pathname.endsWith("/data/snapshot.json")) {
    e.respondWith(
      fetch(req).then((res) => {
        if (res.ok) { const copy = res.clone(); caches.open(CACHE).then((c) => c.put(req, copy)); }
        return res;
      }).catch(() => caches.match(req, { ignoreSearch: true }))
    );
    return;
  }
  e.respondWith(
    caches.match(req, { ignoreSearch: true }).then((hit) => {
      const net = fetch(req).then((res) => {
        if (res.ok) { const copy = res.clone(); caches.open(CACHE).then((c) => c.put(req, copy)); }
        return res;
      }).catch(() => hit || (req.mode === "navigate" ? caches.match("index.html") : undefined));
      return hit || net;
    })
  );
});
