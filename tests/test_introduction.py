"""Homepage introduction media and administrative permissions."""

import re
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import text

import test_regression as fixture


class IntroductionVideo(unittest.TestCase):
    def test_admin_can_add_replace_and_clear_public_video(self):
        client = TestClient(fixture.app, base_url="https://testserver")
        path = "/admin/comercial/video"

        def member(email, role):
            fixture.accounts.register(email, fixture.PASSWORD)
            token = fixture.accounts.login(email, fixture.PASSWORD)
            owner = fixture.accounts.account_for(token)
            with fixture.get_engine().begin() as db:
                db.execute(text("UPDATE accounts SET commercial_role=:role WHERE id=:owner"),
                           {"role": role, "owner": owner})
            return {"Authorization": f"Bearer {token}"}

        with fixture.get_engine().begin() as db:
            db.execute(text("DELETE FROM rate_windows"))
        admin = member("video-admin@example.com", "admin")
        auditor = member("video-auditor@example.com", "auditor")
        original = "https://media.example.com/intro.mp4"
        replacement = "https://media.example.com/new.webm"
        self.assertNotIn("planet-intro-player", client.get("/").text)
        self.assertEqual(client.post(path, data={"url": original}).status_code, 401)
        self.assertEqual(client.post(path, headers=auditor, data={"url": original}).status_code, 403)
        self.assertNotIn(path, client.get("/admin/comercial", headers=auditor).text)
        for invalid in ("http://example.com/video.mp4", "javascript:alert(1)", "https://u:p@example.com/x.mp4",
                        "https://example.com/watch", "https://example.com:8443/video.mp4"):
            self.assertEqual(client.post(path, headers=admin, data={"url": invalid}).status_code, 400)
        self.assertEqual(client.post(path, headers=admin, data={"url": original}, follow_redirects=False).status_code, 303)
        for locale in fixture.LANGUAGES:
            body = client.get("/", headers={"Accept-Language": locale}).text
            self.assertIn("<h1>PLANET-IA</h1>", body)
            self.assertIn(fixture.catalog(locale)["intro.watch"], body)
            video = re.search(r"<video\b[^>]*>", body)[0]
            self.assertIn('preload="none"', video)
            self.assertNotIn("autoplay", video)
            for key, value in fixture.catalog(locale).items():
                for brand in ("Gemini", "PLANET-IA", "Stripe", "GBIF"):
                    if brand in key:
                        self.assertIn(brand, value)
        home = client.get("/", headers={"Accept-Language": "pt-BR"}).text
        self.assertIn("Tudo o que você gostaria de saber sobre as plantas, na palma da sua mão.", home)
        self.assertNotIn("lhe dirá que planta é", home)
        self.assertIn(original, home)
        self.assertIn(original, client.get("/admin/comercial", headers=admin).text)
        self.assertEqual(client.post(path, headers=admin, data={"url": replacement}, follow_redirects=False).status_code, 303)
        self.assertIn(replacement, client.get("/").text)
        self.assertNotIn(original, client.get("/").text)
        self.assertEqual(client.post(path, headers=admin, data={"url": ""}, follow_redirects=False).status_code, 303)
        self.assertNotIn("planet-intro-player", client.get("/").text)
        with fixture.get_engine().connect() as db:
            audit = db.execute(text("SELECT details FROM commercial_audit WHERE action='video.edit' ORDER BY id")).scalars().all()
        self.assertEqual(audit, ['{"enabled": true}', '{"enabled": true}', '{"enabled": false}'])
