// Run through test_health_browser.py with a local, mocked Gemini endpoint.
const assert = require("node:assert/strict");
const { chromium } = require("playwright");

async function run() {
    const origin = process.env.PLANET_TEST_ORIGIN;
    assert.equal(new URL(origin).hostname, "127.0.0.1");
    const path = process.env.PLANET_TEST_PATH;
    const browser = await chromium.launch(process.env.PLANET_CHROMIUM
        ? { executablePath: process.env.PLANET_CHROMIUM } : {});
    try {
        const context = await browser.newContext({
            baseURL: origin, locale: "pt-BR", viewport: { width: 390, height: 844 },
            isMobile: true, hasTouch: true, serviceWorkers: "block"
        });
        await context.addCookies([{
            name: "planet_session", value: process.env.PLANET_TEST_TOKEN, url: origin
        }]);
        await context.route(/^https?:\/\/(?!127\.0\.0\.1:)/, route => route.abort());
        const page = await context.newPage();
        page.setDefaultTimeout(10000);
        assert.equal((await page.goto(path)).status(), 200);
        const form = page.locator("#health-diagnosis");
        const submit = form.getByRole("button", { name: "Diagnosticar minha planta" });
        const alert = form.getByRole("alert");
        const gallery = form.locator('[name="photo"]');
        const camera = form.locator("[capture=environment]");
        const symptoms = form.locator("[name=symptoms]");
        await camera.waitFor();
        assert.equal(await symptoms.isVisible(), false);
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
        await submit.click();
        await alert.getByText("Tire ou escolha uma foto para continuar.").waitFor();
        await gallery.setInputFiles({ name: "invalid.jpg", mimeType: "image/jpeg", buffer: Buffer.from("not a JPEG") });
        await submit.click();
        await alert.getByText("Não foi possível abrir a foto.", { exact: false }).waitFor();

        await form.getByText("Adicionar informações", { exact: true }).click();
        await symptoms.fill("Manchas nas folhas");
        await form.locator('[name="watering"]').selectOption("weekly");
        const largePhoto = await page.evaluate(() => {
            const canvas = document.createElement("canvas");
            canvas.width = 4000;
            canvas.height = 3000;
            const ctx = canvas.getContext("2d");
            const pixels = ctx.createImageData(canvas.width, canvas.height);
            let random = 37;
            for (let i = 0; i < pixels.data.length; i += 4) {
                random = (Math.imul(1664525, random) + 1013904223) | 0;
                pixels.data[i] = random >>> 24;
                pixels.data[i + 1] = random >>> 16;
                pixels.data[i + 2] = random >>> 8;
                pixels.data[i + 3] = 255;
            }
            ctx.putImageData(pixels, 0, 0);
            return canvas.toDataURL("image/jpeg", 0.96).split(",")[1];
        });
        const photo = Buffer.from(largePhoto, "base64");
        assert(photo.length > 2 * 1024 * 1024);
        const endpoint = "/api" + path + "/avaliar";
        const direct = await context.request.post(endpoint, {
            headers: { Origin: origin },
            multipart: { photo: { name: "phone.jpg", mimeType: "image/jpeg", buffer: photo } }
        });
        assert.equal(direct.status(), 413);
        await camera.setInputFiles({ name: "phone.jpg", mimeType: "image/jpeg", buffer: photo });
        assert.equal(await gallery.evaluate(el => el.files.length), 0);
        await page.route(endpoint, route => route.fulfill({ status: 413 }), { times: 1 });
        await submit.click();
        await alert.getByText("A foto é grande demais.", { exact: false }).waitFor();
        assert.equal(await symptoms.inputValue(), "Manchas nas folhas");
        assert.equal(await form.locator('[name="watering"]').inputValue(), "weekly");
        assert.equal(await camera.evaluate(el => el.files[0].name), "phone.jpg");
        await page.route(endpoint, route => route.abort(), { times: 1 });
        await submit.click();
        await alert.getByText("Não foi possível concluir o diagnóstico.", { exact: false }).waitFor();
        assert.equal(await camera.evaluate(el => el.files[0].name), "phone.jpg");

        const request = page.waitForRequest(url => url.url().endsWith(endpoint));
        await submit.click();
        const body = (await request).postDataBuffer();
        assert(body.length < 2 * 1024 * 1024);
        await page.waitForURL(/#event-\d+$/);
        const event = page.locator(".health-event").first();
        await event.getByRole("heading", { name: "Possíveis problemas" }).waitFor();
        await event.getByRole("heading", { name: "Como cuidar da planta" }).waitFor();
        await page.waitForFunction(() => document.activeElement.id === location.hash.slice(1));
        console.log("Chromium mobile: original JPEG size", photo.length, "multipart size", body.length);
    } finally {
        await browser.close();
    }
}
run().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
