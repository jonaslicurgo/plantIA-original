// Run locally with Playwright and an isolated test server. No external services are used.
const assert = require("node:assert/strict");
const { chromium } = require("playwright");

async function run() {
    const origin = process.env.PLANET_TEST_ORIGIN || "http://127.0.0.1:8893";
    assert.equal(new URL(origin).hostname, "127.0.0.1");
    const browser = await chromium.launch(process.env.PLANET_CHROMIUM
        ? { executablePath: process.env.PLANET_CHROMIUM } : {});
    try {
        const context = await browser.newContext({ baseURL: origin, locale: "pt-BR" });
        await context.route(/^https?:\/\/(?!127\.0\.0\.1:)/, route => route.abort());
        const page = await context.newPage();
        const login = await context.request.post("/conta/entrar", {
            headers: { Origin: origin },
            form: { email: "pwa-fixture@example.com", password: "Local-pwa-test-password" },
            maxRedirects: 0
        });
        assert.equal(login.status(), 303);
        assert.equal((await page.goto("/privacidade")).status(), 200);
        await page.locator('link[rel="manifest"]').waitFor({ state: "attached" });
        await page.evaluate(() => navigator.serviceWorker.ready.then(() => true));
        await page.waitForFunction(() => Boolean(navigator.serviceWorker.controller));
        await page.locator('form[action="/privacidade/excluir"]').waitFor();
        for (const width of [320, 390, 768, 1280]) {
            await page.setViewportSize({ width, height: 900 });
            assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
        }
        assert.equal((await page.goto("/assinatura")).status(), 200);
        const keys = await page.evaluate(async () =>
            (await (await caches.open("planet-public-offline-v1")).keys()).map(r => new URL(r.url).pathname));
        assert.deepEqual(keys, ["/static/pwa/offline.html"]);
        await context.setOffline(true);
        await page.goto("/privacidade");
        await page.getByText("Sem conexão.", { exact: false }).waitFor();
        assert.equal(await page.locator('form[action="/privacidade/excluir"]').count(), 0);
        await page.goto("/assinatura");
        await page.getByText("Sem conexão.", { exact: false }).waitFor();
        await context.setOffline(false);
        await page.goto("/privacidade");
        await page.locator('form[action="/privacidade/excluir"]').waitFor();
        const logout = await context.request.post("/conta/sair", {
            headers: { Origin: origin }, maxRedirects: 0
        });
        assert.equal(logout.status(), 303);
        await page.goto("/privacidade");
        assert.equal(await page.locator('form[action="/privacidade/excluir"]').count(), 0);
        console.log("Chromium: PWA, 4 larguras, navegação online, cache público e queda/retorno da conexão.");
    } finally {
        await browser.close();
    }
}
run().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
