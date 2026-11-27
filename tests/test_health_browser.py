"""Isolated browser-to-Gemini contract test (enable with PLANET_HEALTH_BROWSER_TEST=1)."""

import os
from pathlib import Path
import socket
import subprocess
from threading import Thread
from time import monotonic, sleep
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image
import uvicorn

import test_regression as fixture
from plantia import commercial


@unittest.skipUnless(os.getenv("PLANET_HEALTH_BROWSER_TEST") == "1", "requires Playwright and Chromium")
class HealthBrowser(unittest.TestCase):
    def test_large_phone_photo_retry_and_diagnosis(self):
        email = "health-browser@example.com"
        fixture.accounts.register(email, fixture.PASSWORD)
        token = fixture.accounts.login(email, fixture.PASSWORD)
        owner = fixture.accounts.account_for(token)
        fixture.grant_fixture_subscription(owner, "plus_monthly")
        with commercial.transaction() as db:
            db.execute(fixture.text("DELETE FROM rate_windows"))
        headers = {"Authorization": f"Bearer {token}"}
        api = TestClient(fixture.app, base_url="https://testserver")
        with patch.object(fixture.GeminiService, "identificar", return_value=fixture.IdentificacionGemini(
            nombre_comun="Fern", nombre_cientifico="Dryopteris filix-mas",
        )):
            plant = api.post("/api/plantas/identificar", files=fixture.photo(), headers=headers)
        self.assertEqual(plant.status_code, 200, plant.text)
        path = f"/plantas/{plant.json()['id']}/saude"

        for locale in fixture.LANGUAGES:
            page = api.get(path, headers={**headers, "Accept-Language": locale})
            self.assertEqual(page.status_code, 200)
            for key in ("choose_photo", "take_photo", "add_information", "diagnose_plant", "photo_invalid",
                        "photo_missing", "photo_large", "submit_failed", "diagnosing"):
                self.assertIn(fixture.catalog(locale)[f"health.{key}"], page.text)

        with socket.socket() as listener, patch.object(fixture.GeminiService, "_get_client") as client:
            generate = client.return_value.models.generate_content
            generate.return_value.text = (
                '{"status":"possible","concern":"low","signs":["spots"],"findings":["fungal"]}'
            )
            listener.bind(("127.0.0.1", 0))
            origin = f"http://127.0.0.1:{listener.getsockname()[1]}"
            server = uvicorn.Server(uvicorn.Config(fixture.app, lifespan="off", log_level="warning"))
            thread = Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
            with patch.dict(os.environ, {"PLANET_PUBLIC_ORIGIN": origin}):
                thread.start()
                try:
                    deadline = monotonic() + 5
                    while not server.started and thread.is_alive() and monotonic() < deadline:
                        sleep(0.02)
                    self.assertTrue(server.started)
                    subprocess.run(["node", str(Path(__file__).with_name("health_browser.cjs"))], check=True,
                                   timeout=60, env={**os.environ, "PLANET_TEST_ORIGIN": origin,
                                                    "PLANET_TEST_PATH": path, "PLANET_TEST_TOKEN": token})
                finally:
                    server.should_exit = True
                    thread.join(5)
            generate.assert_called_once()
            payload = generate.call_args.kwargs["contents"]
            self.assertIn("Manchas nas folhas", payload[1])
            image = payload[2].inline_data
            self.assertEqual(image.mime_type, "image/jpeg")
            self.assertLess(len(image.data), 2 * 1024 * 1024)
            with Image.open(fixture.BytesIO(image.data)) as normalized:
                self.assertEqual(normalized.size, (1440, 1080))
                self.assertFalse(normalized.getexif())
