if ("serviceWorker" in navigator && window.isSecureContext) {
    navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => {
        // Installation is optional. The online app remains available.
    });
}

// An authenticated document restored from browser history must recheck the session.
if (document.body.hasAttribute("data-private-page")) {
    window.addEventListener("pagehide", () => { document.body.style.visibility = "hidden"; });
    window.addEventListener("pageshow", event => { if (event.persisted) location.reload(); });
}
