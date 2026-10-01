const CACHE_NAME = "a3-crm-v2";
const STATIC_PREFIX = "/static/";
const MAX_RUNTIME_ENTRIES = 120;

const PRECACHE = [
    "/login",
    "/static/app.css",
    "/static/icon-192.png",
    "/static/icon-512.png",
    "/static/apple-touch-icon.png",
    "/static/favicon.svg",
    "/static/manifest.json"
];

self.addEventListener("install", function (event) {
    event.waitUntil(
        caches.open(CACHE_NAME).then(function (cache) {
            return cache.addAll(PRECACHE);
        }).then(function () {
            return self.skipWaiting();
        })
    );
});

self.addEventListener("activate", function (event) {
    event.waitUntil(
        caches.keys().then(function (keys) {
            return Promise.all(
                keys.map(function (key) {
                    if (key !== CACHE_NAME) {
                        return caches.delete(key);
                    }
                })
            );
        }).then(function () {
            return self.clients.claim();
        })
    );
});

function trimRuntimeCache(cache) {
    return cache.keys().then(function (keys) {
        if (keys.length <= MAX_RUNTIME_ENTRIES) {
            return;
        }
        var excess = keys.length - MAX_RUNTIME_ENTRIES;
        var deletions = [];
        for (var i = 0; i < excess; i++) {
            deletions.push(cache.delete(keys[i]));
        }
        return Promise.all(deletions);
    });
}

self.addEventListener("fetch", function (event) {
    var request = event.request;

    if (request.method !== "GET") {
        return;
    }

    var url = new URL(request.url);

    if (url.origin !== self.location.origin) {
        return;
    }

    if (url.pathname.indexOf(STATIC_PREFIX) === 0) {
        event.respondWith(
            caches.match(request).then(function (cached) {
                if (cached) {
                    return cached;
                }
                return fetch(request).then(function (response) {
                    if (response && response.ok) {
                        var copy = response.clone();
                        caches.open(CACHE_NAME).then(function (cache) {
                            cache.put(request, copy);
                        });
                    }
                    return response;
                });
            })
        );
        return;
    }

    if (request.mode === "navigate") {
        event.respondWith(
            fetch(request).then(function (response) {
                if (response && response.ok) {
                    var copy = response.clone();
                    caches.open(CACHE_NAME).then(function (cache) {
                        cache.put(request, copy).then(function () {
                            trimRuntimeCache(cache);
                        });
                    });
                }
                return response;
            }).catch(function () {
                return caches.match(request).then(function (cached) {
                    if (cached) {
                        return cached;
                    }
                    return caches.match("/login");
                });
            })
        );
    }
});
