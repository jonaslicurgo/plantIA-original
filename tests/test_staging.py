"""HTTP journeys for staging controls with isolated SQLite and simulated providers."""

import json
import os
import tempfile
import unittest
from unittest.mock import patch

import test_regression as fixture
from fastapi.testclient import TestClient
from sqlalchemy import text

from scripts.run_staging import validate


class Staging(unittest.TestCase):
    def setUp(self):
        with fixture.get_engine().begin() as db:
            db.execute(text("DELETE FROM rate_windows"))
        self.client = TestClient(fixture.app, base_url="https://testserver")

    def test_verified_signup_to_private_garden_and_account_erasure(self):
        from plantia import commercial
        with commercial.transaction() as db:
            original = commercial.rules(db)
            db.execute(text("UPDATE commercial_rules SET payload=:value"), {
                "value": original.model_copy(update={"free_diagnosis": True}).model_dump_json()})
        def restore():
            with commercial.transaction() as db:
                db.execute(text("UPDATE commercial_rules SET payload=:value"), {"value": original.model_dump_json()})
        self.addCleanup(restore)
        email = "stage-member@example.com"
        login = {"email": email, "password": fixture.PASSWORD}
        other = {"email": "stage-other@example.com", "password": fixture.PASSWORD}
        with patch.dict(os.environ, {"PLANET_REQUIRE_VERIFIED_EMAIL": "1"}), \
             patch.object(fixture.accounts, "send_verification") as sender:
            self.assertEqual(self.client.post("/api/auth/register", data=login).status_code, 202)
            code = sender.call_args.args[1]
            self.assertEqual(self.client.post("/api/auth/login", data=login).status_code, 403)
            self.assertEqual(self.client.post("/api/auth/resend-verification", data={"email": email}).status_code, 202)
            replacement = sender.call_args.args[1]
            self.assertNotEqual(code, replacement)
            for token, password in ((code, fixture.PASSWORD), (replacement, fixture.NEW_PASSWORD)):
                self.assertEqual(self.client.post("/api/auth/verify", data={"token": token, "password": password}).status_code, 400)
            verify = {"token": replacement, "password": fixture.PASSWORD}
            self.assertEqual(self.client.post("/api/auth/verify", data=verify).status_code, 200)
            self.assertEqual(self.client.post("/api/auth/verify", data=verify).status_code, 400)
            session = self.client.post("/api/auth/login", data=login).json()
            self.assertEqual(self.client.post("/api/auth/register", data=other).status_code, 202)
            self.assertEqual(self.client.post("/api/auth/verify", data={
                "password": fixture.PASSWORD, "token": sender.call_args.args[1]
            }).status_code, 200)
            other_session = self.client.post("/api/auth/login", data=other).json()
            a = {"Authorization": "Bearer " + session["access_token"]}
            b = {"Authorization": "Bearer " + other_session["access_token"]}

            with patch.object(fixture.GeminiService, "identificar", return_value=fixture.IdentificacionGemini(
                nombre_comun="Test fern", nombre_cientifico="Dryopteris filix-mas"
            )), patch("plantia.services.health.analyze", return_value=fixture.Triage(
                status="possible", concern="high", signs=["webbing"], findings=["mites"]
            )):
                created = self.client.post("/api/plantas/identificar", files=fixture.photo(), headers=a)
                self.assertEqual(created.status_code, 200, created.text)
                item = created.json()
                plant = item["id"]
                health = self.client.post(f"/api/plantas/{plant}/saude/avaliar",
                    files={"photo": fixture.photo()["file"]}, headers=a)
                self.assertEqual(health.status_code, 201, health.text)
            with patch("plantia.services.botany.get_taxon", return_value={}):
                self.assertEqual(self.client.get(f"/api/enciclopedia/{plant}", headers=a).status_code, 200)
            self.assertEqual(self.client.get(f"/api/enciclopedia/{plant}", headers=b).status_code, 404)
            form = {"kind": "water", "due_on": "2030-01-01"}
            task = self.client.post(f"/api/jardim/{plant}/tarefas", data=form, headers=a)
            self.assertEqual(task.status_code, 201, task.text)
            self.assertEqual(self.client.post(f"/api/jardim/{plant}/tarefas/{task.json()['id']}/concluir",
                headers=a).status_code, 200)
            self.assertEqual(self.client.get("/api/assinatura", headers=a).json()["usage"]["remaining"], 1)
            self.assertEqual(self.client.get("/admin/comercial", headers=a).status_code, 403)
            self.assertEqual(self.client.post("/api/auth/delete", data={"password": fixture.PASSWORD}, headers=a).status_code, 400)
            self.assertEqual(self.client.post("/api/auth/delete", data={"password": fixture.NEW_PASSWORD, "confirm": True}, headers=a).status_code, 403)
            self.assertEqual(self.client.post("/api/auth/delete", data={"password": fixture.PASSWORD, "confirm": True}, headers=a).status_code, 200)
            self.assertEqual(self.client.get("/api/assinatura", headers=a).status_code, 401)
            self.assertEqual(self.client.get("/api/assinatura", headers=b).status_code, 200)
            self.assertFalse((fixture.UPLOADS_DIR / item["image_path"]).exists())
            with fixture.get_engine().connect() as db:
                for table in ("plantas", "garden_tasks", "plant_health_events", "health_ai_usage", "ai_meter"):
                    key = "id" if table == "plantas" else "account_id" if table == "ai_meter" else "plant_id"
                    value = session["account_id"] if table == "ai_meter" else plant
                    self.assertFalse(db.exec_driver_sql(f"SELECT 1 FROM {table} WHERE {key}=?", (value,)).first())

    def test_administrator_and_stripe_linked_account_deletion_protection(self):
        for label in ("operator", "billing"):
            with self.subTest(label=label):
                email = f"stage-{label}@example.com"
                fixture.accounts.register(email, fixture.PASSWORD)
                token = fixture.accounts.login(email, fixture.PASSWORD)
                owner = fixture.accounts.account_for(token)
                with fixture.get_engine().begin() as db:
                    if label == "operator":
                        db.execute(text("UPDATE accounts SET commercial_role='admin' WHERE id=:id"), {"id": owner})
                    else:
                        db.execute(text("INSERT INTO billing_customers VALUES (:id,'stripe','cus_testdelete')"), {"id": owner})
                headers = {"Authorization": "Bearer " + token}
                with patch.dict(os.environ, {"PLANET_REQUIRE_VERIFIED_EMAIL": "1"}):
                    self.assertEqual(self.client.get("/admin/comercial", headers=headers, follow_redirects=False)
                                     .headers["location"], "/conta/verificar")
                    self.assertEqual(self.client.post("/api/auth/delete", data={
                        "password": fixture.PASSWORD, "confirm": True
                    }, headers=headers).status_code, 409)
                self.assertEqual(fixture.accounts.account_for(token), owner)

    def test_staging_launcher_rejects_unsafe_settings(self):
        with tempfile.TemporaryDirectory() as mount:
            valid = {
                "PLANET_DEPLOYMENT": "staging", "PLANET_DATA_DIR": mount,
                "RAILWAY_VOLUME_MOUNT_PATH": mount, "PLANET_PUBLIC_ORIGIN": "https://stage.example.com",
                "RAILWAY_PUBLIC_DOMAIN": "stage.example.com", "PLANET_REQUIRE_VERIFIED_EMAIL": "1",
                "PLANET_RESEND_API_KEY": "re_fixture", "PLANET_RESEND_FROM": "onboarding@resend.dev",
                "PLANET_STRIPE_KEY": "sk_test_fixture",
            }
            validate(valid)
            for key, value in (
                ("PLANET_DEPLOYMENT", "production"), ("RAILWAY_ENVIRONMENT_NAME", "production"), ("PLANET_DATA_DIR", "/other"),
                ("PLANET_PUBLIC_ORIGIN", "http://stage.example.com"), ("PLANET_INSECURE_LOCAL_HTTP", "1"),
                ("RAILWAY_PUBLIC_DOMAIN", "production.example.com"), ("PLANET_REQUIRE_VERIFIED_EMAIL", "0"),
                ("PLANET_STRIPE_KEY", "sk_live_fixture"), ("PLANET_RESEND_API_KEY", ""), ("PLANET_RESEND_FROM", ""),
            ):
                with self.subTest(key=key), self.assertRaises(ValueError):
                    validate({**valid, key: value})

    def test_resend_sends_localized_codes_and_rejects_redirects(self):
        with patch("plantia.accounts.HTTPSConnection") as https:
            conn = https.return_value
            response = conn.getresponse.return_value
            response.status = 200
            for send, page in ((fixture.accounts.send_verification, "verificar"),
                               (fixture.accounts.send_recovery, "redefinir")):
                send("recipient@example.com", "fixture-code", "pt-BR")
                args, kwargs = conn.request.call_args
                self.assertEqual(args, ("POST", "/emails"))
                mail = json.loads(kwargs["body"])
                self.assertEqual(mail["from"], "onboarding@resend.dev")
                self.assertEqual(mail["to"], ["recipient@example.com"])
                self.assertEqual(kwargs["headers"]["Authorization"], "Bearer re_fixture")
                self.assertIn(f"https://testserver/conta/{page}\n", mail["text"])
                self.assertTrue(mail["text"].endswith("fixture-code"))
            https.assert_called_with("api.resend.com", timeout=10)
            for status in (307, 403, 429, 500):
                response.status = status
                with self.assertRaisesRegex(OSError, rf"^Resend rejected email \(HTTP {status}\)$"):
                    fixture.accounts.send_verification("recipient@example.com", "fixture-code", "pt-BR")
            self.assertEqual(conn.request.call_count, 6)
            response.read.assert_not_called()

    def test_resend_error_does_not_expose_response_body_or_change_public_reply(self):
        self.client.post("/api/auth/register", data={
            "email": "resend-failure@example.com", "password": fixture.PASSWORD,
        })
        with patch("plantia.accounts.HTTPSConnection") as https, self.assertLogs("plantia.api.auth", "WARNING") as logs:
            response = https.return_value.getresponse.return_value
            response.status = 403
            result = self.client.post("/api/auth/recover", data={"email": "resend-failure@example.com"})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(logs.output, ["WARNING:plantia.api.auth:PLANET-IA recovery email delivery failed"])
        response.read.assert_not_called()

    def test_public_pwa_and_private_cache_headers(self):
        self.assertEqual(self.client.get("/health").json(), {"status": "ok"})
        self.assertIn("javascript", self.client.get("/sw.js").headers["content-type"])
        self.assertEqual(self.client.get("/static/pwa/manifest.webmanifest").json()["display"], "standalone")
        self.assertEqual(self.client.get("/privacidade").status_code, 200)
        self.assertEqual(self.client.get("/privacidade").headers["cache-control"], "private, no-store")
        for locale in fixture.LANGUAGES:
            self.assertIn("privacy.delete", fixture.catalog(locale))
