const cacheName = "planet-public-offline-v1";
const offlinePage = "/static/pwa/offline.html";

self.addEventListener("install", event => {
    event.waitUntil((async () => {
        const cache = await caches.open(cacheName);
        const response = await fetch(offlinePage, { credentials: "omit", cache: "reload", redirect: "error" });
        if (!response.ok) throw new Error("Offline page unavailable");
        await cache.put(offlinePage, response);
        await self.skipWaiting();
    })());
});

self.addEventListener("activate", event => {
    event.waitUntil((async () => {
        for (const name of await caches.keys()) {
            if (name.startsWith("planet-public-offline-") && name !== cacheName) await caches.delete(name);
        }
        await self.clients.claim();
    })());
});

self.addEventListener("fetch", event => {
    const request = event.request;
    if (request.method !== "GET" || request.mode !== "navigate" ||
        new URL(request.url).origin !== self.location.origin) return;
    // Private pages always go to the network. A failure shows a public, generic document.
    event.respondWith(fetch(request, { cache: "no-store" }).catch(async () => {
        const cache = await caches.open(cacheName);
        return await cache.match(offlinePage) || Response.error();
    }));
});
