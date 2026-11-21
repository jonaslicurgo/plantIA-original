"""Run only through the isolated test launcher documented in CHANGELOG.md."""

from io import BytesIO
from pathlib import Path
import os
import tempfile
import sqlite3
import subprocess
import sys
import unittest
from urllib.error import URLError
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import text

# Never inherit a real database, Gemini key or mail transport.
data = tempfile.TemporaryDirectory(prefix="planet-ia-test-")
os.environ["PLANET_DATA_DIR"] = data.name
os.environ["GEMINI_API_KEY"] = ""
os.environ["GEMINI_MODEL"] = "gemini-3.1-flash-lite"
os.environ["PLANET_PUBLIC_ORIGIN"] = "https://testserver"
os.environ["PLANET_INSECURE_LOCAL_HTTP"] = "0"
os.environ["PLANET_SMTP_HOST"] = "mail.invalid"
os.environ["PLANET_SMTP_FROM"] = "planet@example.com"

from main import app
from plantia import accounts
from plantia.database import get_engine
from plantia.config import UPLOADS_DIR
from plantia.i18n import LANGUAGES, catalog
from plantia.schemas.planta import IdentificacionGemini
from plantia.services.health import Action, AssistantReply, Finding, Sign, Triage
from plantia.services.botany import GROUPS, SPECIES, _fetch_taxon
from plantia.services.gemini_service import GeminiService

PASSWORD = "A-test-password-long"
NEW_PASSWORD = "Another-long-test-password"
ORIGIN = {"Origin": "https://testserver"}


def photo():
    buffer = BytesIO()
    Image.new("RGB", (32, 32)).save(buffer, "JPEG")
    return {"file": ("leaf.jpg", buffer.getvalue(), "image/jpeg")}


class Regression(unittest.TestCase):
    def setUp(self):
        self.a = TestClient(app, base_url="https://testserver")
        self.b = TestClient(app, base_url="https://testserver")
        with get_engine().begin() as db:
            db.execute(text("DELETE FROM rate_windows"))
        self.mock = patch.object(GeminiService, "identificar", return_value=IdentificacionGemini(nombre_comun="Test fern", nombre_cientifico="Dryopteris filix-mas"))
        self.identify = self.mock.start()
        self.addCleanup(self.mock.stop)

    def account(self, client, email, password=PASSWORD):
        client.post("/api/auth/register", data={"email": email, "password": password})
        response = client.post("/api/auth/login", data={"email": email, "password": password})
        self.assertEqual(response.status_code, 200, response.text)
        return {"Authorization": "Bearer " + response.json()["access_token"]}

    def test_private_records_and_photos_two_accounts(self):
        a = self.account(self.a, "owner@example.com")
        b = self.account(self.b, "other@example.com")
        self.assertEqual(self.a.get("/api/plantas").status_code, 401)
        result = self.a.post("/api/plantas/identificar", files=photo(), headers=a)
        self.assertEqual(result.status_code, 200, result.text)
        item = result.json()
        url = f"/api/plantas/{item['id']}"
        web = f"/plantas/{item['id']}"
        img = f"/uploads/{item['image_path']}"
        self.assertEqual(self.a.get(img).status_code, 401)
        self.assertEqual(self.a.get(img, headers=a).status_code, 200)
        self.assertEqual(self.a.get(img, headers=a).headers["cache-control"], "private, no-store")
        self.assertEqual(self.b.get(img, headers=b).status_code, 404)
        self.assertEqual(self.b.get(url, headers=b).status_code, 404)
        self.assertEqual(self.b.get(web, headers=b).status_code, 404)
        self.assertEqual(self.b.get("/api/plantas?q=fern", headers=b).json()["total"], 0)
        self.assertEqual(self.a.get("/api/plantas?q=fern", headers=a).json()["total"], 1)
        self.assertEqual(self.b.patch(url, json={"notas_usuario":"unauthorized"}, headers=b).status_code, 404)
        self.assertEqual(self.b.post(url + "/notas", json={"notas_usuario":"unauthorized"}, headers=b).status_code, 404)
        self.assertEqual(self.b.delete(url, headers=b).status_code, 404)
        self.assertEqual(self.a.patch(url, json={"notas_usuario":"watered"}, headers=a).json()["notas_usuario"], "watered")
        self.assertEqual(self.a.delete(url, headers=a).status_code, 204)
        self.assertEqual(self.a.get(img, headers=a).status_code, 404)

    def test_password_recovery_and_revocation(self):
        email = "reset@example.com"
        headers = self.account(self.a, email)
        with patch.object(accounts, "send_recovery") as send:
            sent = self.a.post("/api/auth/recover", data={"email": email})
            absent = self.a.post("/api/auth/recover", data={"email": "absent@example.com"})
        self.assertEqual(sent.json(), absent.json())
        token = send.call_args.args[1]
        data = {"token": token, "password": NEW_PASSWORD}
        self.assertEqual(self.a.post("/api/auth/reset", data=data).status_code, 200)
        self.assertEqual(self.a.post("/api/auth/reset", data=data).status_code, 400)
        self.assertEqual(self.a.get("/api/plantas", headers=headers).status_code, 401)
        login = self.a.post("/api/auth/login", data={"email": email, "password": NEW_PASSWORD})
        self.assertEqual(login.status_code, 200)

    def test_web_locales_and_origin(self):
        email = "web@example.com"
        self.account(self.a, email)
        self.assertEqual(self.a.post("/conta/entrar", data={"email": email, "password": PASSWORD}, headers=ORIGIN, follow_redirects=False).status_code, 303)
        for locale in LANGUAGES:
            page = self.b.get("/conta/entrar", headers={"Accept-Language":locale})
            self.assertIn(f'lang="{locale}"', page.text)
            self.assertIn(catalog(locale)["Sign in"], page.text)
        self.assertIn('dir="rtl"', self.b.get("/", headers={"Accept-Language":"ar"}).text)
        self.a.post("/idioma", data={"language":"ja", "page":"/"}, headers=ORIGIN)
        self.assertIn('lang="ja"', self.a.get("/", headers={"Accept-Language":"de"}).text)
        self.assertEqual(self.a.post("/identificar", files=photo(), headers={"Origin":"https://external.invalid"}).status_code,403)
        self.assertEqual(self.a.post("/identificar", files=photo(), headers=ORIGIN).status_code,200)
        self.assertEqual(self.identify.call_args.args[2],"Japanese")
        for path in ("/configuracion", "/salir"):
            self.assertEqual(self.a.post(path, data={"dummy":"x"}, headers=ORIGIN).status_code,404)
        self.assertEqual(self.a.post("/conta/sair", data={"dummy":"x"}, headers=ORIGIN, follow_redirects=False).status_code,303)
        self.assertEqual(self.a.get("/api/plantas").status_code,401)

    def test_upload_limits_and_validation(self):
        headers = self.account(self.a, "upload@example.com")
        for endpoint in ("/identificar","/api/plantas/identificar"):
            self.assertEqual(self.a.post(endpoint, files={"file":("x.txt",b"x","text/plain")}, headers=headers).status_code,400)
            self.assertEqual(self.a.post(endpoint, files={"file":("x.jpg",b"x","image/jpeg")}, headers=headers).status_code,400)
            self.assertEqual(self.a.post(endpoint, files={"file":("x.jpg",b"x"*(10*1024*1024+1),"image/jpeg")}, headers=headers).status_code,413)
        self.identify.assert_not_called()

    def test_quota_and_legacy_rows(self):
        headers = self.account(self.a, "quota@example.com")
        item = self.a.post("/api/plantas/identificar", files=photo(), headers=headers).json()
        with get_engine().begin() as db:
            db.execute(text("UPDATE plantas SET owner_id=NULL WHERE id=:id"), {"id":item["id"]})
        self.assertEqual(self.a.get(f"/api/plantas/{item['id']}", headers=headers).status_code,404)
        self.assertEqual(self.a.get("/uploads/"+Path(item["image_path"]).name, headers=headers).status_code,404)
        for _ in range(14):
            self.assertEqual(self.a.post("/api/plantas/identificar", files=photo(), headers=headers).status_code,200)
        self.assertEqual(self.a.post("/api/plantas/identificar", files=photo(), headers=headers).status_code,429)

    def test_missing_gemini_configuration_returns_503(self):
        self.mock.stop()
        headers = self.account(self.a, "no-key@example.com")
        self.assertEqual(self.a.post("/api/plantas/identificar", files=photo(), headers=headers).status_code, 503)

    def test_existing_sqlite_migration_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            dbfile = Path(directory) / "plantia.db"
            with sqlite3.connect(dbfile) as db:
                db.execute("CREATE TABLE plantas (id INTEGER PRIMARY KEY, nombre_comun TEXT, nombre_cientifico TEXT)")
                db.execute("INSERT INTO plantas VALUES (7, 'Legacy', '')")
            environment = dict(os.environ, PLANET_DATA_DIR=directory)
            for _ in range(2):
                subprocess.run([sys.executable, "-B", "-c", "from main import app"], env=environment, check=True)
            with sqlite3.connect(dbfile) as db:
                self.assertEqual(db.execute("SELECT id, nombre_comun, owner_id, encyclopedia_favorite FROM plantas").fetchall(),
                                 [(7, "Legacy", None, 0)])
                self.assertEqual(db.execute("SELECT count(*) FROM accounts").fetchone()[0], 0)

    def test_encyclopedia_filters_profile_and_private_favorites(self):
        a = self.account(self.a, "botany-owner@example.com")
        b = self.account(self.b, "botany-other@example.com")
        self.identify.return_value = IdentificacionGemini(
            nombre_comun="Golden pothos", nombre_cientifico="Epipremnum aureum", confianza="alto"
        )
        item = self.a.post("/api/plantas/identificar", files=photo(), headers=a).json()
        url = f"/api/enciclopedia/{item['id']}"
        self.assertEqual(self.a.get(url).status_code, 401)
        self.assertEqual(self.b.get(url, headers=b).status_code, 404)
        self.assertEqual(self.b.patch(url + "/favorito", json={"favorite": True}, headers=b).status_code, 404)
        self.assertEqual(self.b.get("/api/enciclopedia", headers=b).json()["total"], 0)

        self.assertEqual(self.a.get("/api/enciclopedia", headers=a, params={"q": "epipremnum"}).json()["total"], 1)
        self.assertEqual(self.a.get("/api/enciclopedia", headers=a, params={"q": "JIBÓIA", "category": "toxic"}).json()["total"], 1)
        self.assertEqual(self.a.get("/api/enciclopedia", headers=a, params={"category": "medicinal"}).json()["total"], 0)
        self.assertEqual(self.a.get("/api/enciclopedia", headers=a, params={"category": "invented"}).status_code, 400)
        self.assertEqual(self.a.get("/api/enciclopedia", headers=a, params={"favorite": True}).json()["total"], 0)
        self.assertEqual(self.a.patch(url + "/favorito", json={"favorite": True}, headers=a).json(), {"favorite": True})
        self.assertEqual(self.a.get("/api/enciclopedia", headers=a, params={"favorite": True}).json()["total"], 1)
        self.assertEqual(self.b.get("/api/enciclopedia", headers=b, params={"favorite": True}).json()["total"], 0)
        self.assertEqual(self.a.patch(url + "/favorito", json={"favorite": "true"}, headers=a).status_code, 422)

        with patch("plantia.services.botany._fetch_taxon", return_value={
            "key": 2870422, "scientific_name": "Epipremnum aureum", "family": "Araceae"
        }) as fetch:
            doc = self.a.get(url, headers=a).json()
            translated = self.a.get(url, headers={**a, "Accept-Language": "ar"}).json()
            web = self.a.get(f"/enciclopedia/{item['id']}", headers={**a, "Accept-Language": "ar"})
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(self.identify.call_count, 1)
        self.assertEqual(web.status_code, 200, web.text)
        self.assertIn('dir="rtl"', web.text)
        self.assertIn("<details", web.text)
        self.assertEqual(len(doc["groups"]), len(GROUPS))
        fields = {row["key"]: row for group in doc["groups"] for row in group["items"]}
        self.assertEqual(len(fields), 31)
        self.assertEqual(fields["family"]["source"]["label"], "GBIF")
        self.assertEqual(fields["animal_toxicity"]["source"]["label"], "ASPCA Poison Control")
        self.assertIsNone(fields["panc"]["value"])
        self.assertIsNone(fields["panc"]["source"])
        self.assertNotEqual(doc["groups"][0]["title"], translated["groups"][0]["title"])
        self.assertEqual(self.a.patch(url + "/favorito", json={"favorite": False}, headers=a).status_code, 200)
        self.assertFalse(self.a.get(url, headers=a).json()["favorite"])

    def test_inconclusive_does_not_save_a_record_or_photo(self):
        a = self.account(self.a, "uncertain@example.com")
        photos_before = set(UPLOADS_DIR.iterdir())
        for result in (
            IdentificacionGemini(estado_identificacion="inconclusive"),
            IdentificacionGemini(nombre_comun="Weak guess", nombre_cientifico="Aloe vera", confianza="bajo"),
            IdentificacionGemini(nombre_comun="Uncertain genus", nombre_cientifico="Aloe"),
        ):
            self.identify.return_value = result
            api = self.a.post("/api/plantas/identificar", files=photo(), headers={**a, "Accept-Language": "en"})
            self.assertEqual(api.status_code, 422)
            self.assertEqual(api.json()["code"], "identification_inconclusive")
            web = self.a.post("/identificar", files=photo(), headers=a)
            self.assertEqual(web.status_code, 422)
            self.assertIn("Identificação inconclusiva", web.text)
        self.assertEqual(self.a.get("/api/plantas", headers=a).json()["total"], 0)
        self.assertEqual(set(UPLOADS_DIR.iterdir()), photos_before)

    def test_identification_cache_is_scoped_to_owner_and_language(self):
        a = self.account(self.a, "cache-owner@example.com")
        b = self.account(self.b, "cache-other@example.com")
        path = "/api/plantas/identificar"
        first = self.a.post(path, files=photo(), headers=a).json()
        again = self.a.post(path, files=photo(), headers=a).json()
        self.assertEqual(first["id"], again["id"])
        self.assertEqual(self.identify.call_count, 1)
        french = self.a.post(path, files=photo(), headers={**a, "Accept-Language": "fr"}).json()
        other = self.b.post(path, files=photo(), headers=b).json()
        self.assertNotEqual(first["id"], french["id"])
        self.assertNotEqual(first["id"], other["id"])
        self.assertEqual(self.identify.call_count, 3)
        self.a.delete(f"/api/plantas/{first['id']}", headers=a)
        new = self.a.post(path, files=photo(), headers=a).json()
        self.assertNotEqual(first["id"], new["id"])
        self.assertEqual(self.identify.call_count, 4)

    def test_botany_information_absence_and_catalogs(self):
        headers = self.account(self.a, "botany-unknown@example.com")
        created = self.a.post("/api/plantas/identificar", files=photo(), headers=headers).json()
        with patch("plantia.services.botany._fetch_taxon", side_effect=URLError("offline")):
            response = self.a.get(f"/api/enciclopedia/{created['id']}", headers=headers)
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertFalse(result["matched_taxon"])
        fields = {row["key"]: row for group in result["groups"] for row in group["items"]}
        self.assertIsNone(fields["human_toxicity"]["value"])
        self.assertTrue(all(row["source"] is None for row in fields.values()))
        required = {f"botany.field.{field}" for fields in GROUPS.values() for field in fields}
        required.update(fact.message for facts in SPECIES.values() for fact in facts.values())
        for locale in LANGUAGES:
            self.assertTrue(required <= catalog(locale).keys(), locale)

    def test_gbif_accepts_only_exact_plantae_species(self):
        sample = {"usageKey": 2927305, "canonicalName": "Lavandula angustifolia", "rank": "SPECIES",
                  "status": "ACCEPTED", "matchType": "EXACT", "kingdom": "Plantae", "family": "Lamiaceae"}
        from json import dumps
        with patch("plantia.services.botany.urlopen") as urlopen:
            response = urlopen.return_value.__enter__.return_value
            response.read.return_value = dumps(sample).encode()
            self.assertEqual(_fetch_taxon("lavandula angustifolia")["key"], 2927305)
            for invalid in ({"matchType": "FUZZY"}, {"status": "SYNONYM"}, {"kingdom": "Fungi"}, {"canonicalName": "Lavandula latifolia"}):
                response.read.return_value = dumps({**sample, **invalid}).encode()
                self.assertEqual(_fetch_taxon("lavandula angustifolia"), {})

    def test_health_assessment_and_followup_are_private(self):
        a = self.account(self.a, "health-owner@example.com")
        b = self.account(self.b, "health-other@example.com")
        plant = self.a.post("/api/plantas/identificar", files=photo(), headers=a).json()["id"]
        path = f"/api/plantas/{plant}/saude"
        upload = {"photo": photo()["file"]}
        result = Triage(status="possible", concern="high", signs=["webbing"], findings=["mites"])
        with patch("plantia.services.health.analyze", return_value=result) as diagnose:
            self.assertEqual(self.b.post(path + "/avaliar", files=upload, headers=b).status_code, 404)
            diagnose.assert_not_called()
            created = self.a.post(path + "/avaliar", data={"spreading": "true"}, files=upload, headers=a)
            self.assertEqual(created.status_code, 201, created.text)
        event = created.json()
        self.assertIn("specialist", event["actions"])
        self.assertEqual(event["data"]["findings"], ["mites"])
        self.assertNotIn("mime", event["data"])
        image_url = f"{path}/fotos/{event['id']}"
        self.assertEqual(self.a.get(image_url, headers=a).status_code, 200)
        self.assertEqual(self.a.get(image_url, headers=a).headers["cache-control"], "private, no-store")
        self.assertEqual(self.a.get(image_url).status_code, 401)
        self.assertEqual(self.b.get(image_url, headers=b).status_code, 404)
        self.assertEqual(self.b.get(path, headers=b).status_code, 404)
        self.assertEqual(self.b.post(path + "/acompanhar", data={"trend":"stable"}, headers=b).status_code, 404)
        note = "<script>alert(1)</script>"
        follow = self.a.post(path + "/acompanhar", data={"trend":"improving", "note":note}, headers=a)
        self.assertEqual(follow.status_code, 201, follow.text)
        self.assertEqual(self.a.get(path, headers=a).json()["events"][0]["data"]["trend"], "improving")
        web = self.a.get(f"/plantas/{plant}/saude", headers={**a, "Accept-Language":"ar"})
        self.assertEqual(web.status_code, 200, web.text)
        self.assertIn('dir="rtl"', web.text)
        self.assertNotIn(note, web.text)
        self.assertIn("&lt;script&gt;", web.text)
        self.assertEqual(self.a.delete(f"/api/plantas/{plant}", headers=a).status_code, 204)
        self.assertEqual(self.a.get(image_url, headers=a).status_code, 404)
        with get_engine().connect() as db:
            self.assertEqual(db.execute(text("SELECT count(*) FROM plant_health_events WHERE plant_id=:id"), {"id":plant}).scalar(), 0)

    def test_health_rejects_invalid_input_and_unsafe_provider_output(self):
        a = self.account(self.a, "health-validation@example.com")
        plant = self.a.post("/api/plantas/identificar", files=photo(), headers=a).json()["id"]
        path = f"/api/plantas/{plant}/saude/avaliar"
        bad = {"photo": ("sample.jpg", b"not an image", "image/jpeg")}
        self.assertEqual(self.a.post(path, files=bad, headers=a).status_code, 400)
        self.assertEqual(self.a.post(path, files={"photo": photo()["file"]}, data={"moisture":"unknown-other"}, headers=a).status_code, 422)
        oversize = {"photo": ("sample.jpg", b"x"*(2*1024*1024+100000), "image/jpeg")}
        self.assertEqual(self.a.post(path, files=oversize, headers=a).status_code, 413)
        with patch.object(GeminiService, "_get_client") as client:
            generate = client.return_value.models.generate_content
            generate.return_value.text = '{"status":"possible","concern":"high","signs":["spots"],"findings":["fungal"],"advice":"unsafe"}'
            self.assertEqual(self.a.post(path, files={"photo": photo()["file"]}, headers=a).status_code, 503)
            generate.return_value.text = '{"status":"inconclusive","concern":"high","signs":["spots"],"findings":["fungal"]}'
            response = self.a.post(path, files={"photo": photo()["file"]}, headers=a)
            self.assertEqual(response.status_code, 201, response.text)
            self.assertEqual(response.json()["data"]["findings"], [])
            self.assertEqual(response.json()["data"]["concern"], "unknown")
            self.assertEqual(response.json()["actions"], ["observe", "retake"])

    def test_health_comparison_context_and_assistant_usage(self):
        a = self.account(self.a, "p3-owner@example.com")
        b = self.account(self.b, "p3-other@example.com")
        plant = self.a.post("/api/plantas/identificar", files=photo(), headers=a).json()["id"]
        path = f"/api/plantas/{plant}/saude"
        upload = {"photo": photo()["file"]}
        first = Triage(status="possible", concern="high", signs=["dry_leaves"], findings=["temperature_stress"])
        second = Triage(status="possible", concern="moderate", signs=["spots"], findings=["soil_stress", "caterpillars"])
        with patch("plantia.services.health.analyze", side_effect=[first, second]) as provider:
            context = {"temperature":"variable", "watering":"daily", "location":"outside", "environment":"wind"}
            old = self.a.post(path + "/avaliar", data=context, files=upload, headers=a)
            self.assertEqual(old.status_code, 201, old.text)
            duplicate = self.a.post(path + "/avaliar", data=context, files=upload, headers=a)
            self.assertEqual(duplicate.json()["id"], old.json()["id"])
            new = self.a.post(path + "/avaliar", data={**context, "soil":"compacted"}, files=upload, headers=a)
            self.assertEqual(new.status_code, 201, new.text)
            self.assertEqual(provider.call_count, 2)
            self.assertEqual(provider.call_args.args[-1].soil, "compacted")
        self.assertIn("stable_temperature", old.json()["actions"])
        self.assertIn("physical_removal", new.json()["actions"])
        self.assertEqual(new.json()["review_at"] - new.json()["created_at"], 2 * 86400)
        follow = self.a.post(path + "/acompanhar", files=upload, data={
            "trend":"improving", "action":"review_soil", "confirmed_by_specialist":"Recorded by local extension"
        }, headers=a)
        self.assertEqual(follow.status_code, 201, follow.text)
        with patch("plantia.services.health.assist", return_value=AssistantReply(status="guidance", actions=["inspect"])) as ai:
            question = {"question":"What should I check next?"}
            self.assertEqual(self.b.post(path + "/assistente", data=question, headers=b).status_code, 404)
            ai.assert_not_called()
            answer = self.a.post(path + "/assistente", data=question, headers=a)
            duplicate = self.a.post(path + "/assistente", data=question, headers=a)
            self.assertEqual(answer.status_code, 201, answer.text)
            self.assertEqual(duplicate.json()["id"], answer.json()["id"])
            self.assertEqual(ai.call_count, 1)
            self.assertEqual(ai.call_args.args[1]["findings"], ["soil_stress", "caterpillars"])
            self.assertNotIn("context", ai.call_args.args[1])
        history = self.a.get(path, headers=a).json()
        self.assertEqual(history["usage"]["attempts"], 3)
        self.assertEqual(history["usage"]["assessments"], 2)
        self.assertEqual(history["usage"]["assistant"], 1)
        self.assertEqual([item["id"] for item in history["comparison"]["assessments"]], [old.json()["id"], new.json()["id"]])
        self.assertEqual([item["id"] for item in history["comparison"]["photos"]], [new.json()["id"], follow.json()["id"]])
        self.assertEqual(self.b.get(path, headers=b).status_code, 404)
        self.assertEqual(self.a.delete(f"/api/plantas/{plant}", headers=a).status_code, 204)
        from plantia.services.health_usage import totals
        account_id = accounts.account_for(a["Authorization"].split()[1])
        self.assertEqual(totals(account_id)["attempts"], 3)

    def test_health_localization_catalogs_and_assistant_schema(self):
        required = {"health.assistant.out_of_scope", "health.status.no_visible_problem", "health.compare", "health.review",
                    "health.confirmed_label", "health.sources"}
        required |= {"health.finding." + item.value for item in Finding}
        required |= {"health.sign." + item.value for item in Sign}
        required |= {"health.action." + item.value for item in Action}
        for code in LANGUAGES:
            self.assertTrue(required <= catalog(code).keys(), code)
        from plantia.services.health import assist
        with patch.object(GeminiService, "_get_client") as client:
            response = client.return_value.models.generate_content.return_value
            response.text = '{"status":"out_of_scope","actions":["drain"]}'
            self.assertEqual(assist("out of scope", None).actions, [])

    def test_health_ai_single_reservation_and_image_optimization(self):
        from plantia.services import health_usage

        a = self.account(self.a, "p3-reserve@example.com")
        owner = accounts.account_for(a["Authorization"].split()[1])
        plant_id = self.a.post("/api/plantas/identificar", files=photo(), headers=a).json()["id"]
        key = health_usage.fingerprint("assess", "gemini-3.1-flash-lite", {"watering":"weekly"}, b"photo")
        usage_id, cached = health_usage.reserve(owner, plant_id, "assess", key)
        self.assertIsNone(cached)
        with self.assertRaises(health_usage.Busy):
            health_usage.reserve(owner, plant_id, "assess", key)
        health_usage.finish(usage_id, "rejected")
        self.assertEqual(health_usage.totals(owner)["attempts"], 0)
        buffer = BytesIO()
        Image.new("RGB", (1920, 960), "green").save(buffer, "PNG")
        path = f"/api/plantas/{plant_id}/saude/avaliar"
        good = Triage(status="no_visible_problem", concern="low", signs=[], findings=[])
        with patch("plantia.services.health.analyze", return_value=good) as provider:
            result = self.a.post(path, files={"photo":("large.png", buffer.getvalue(), "image/png")}, headers=a)
        self.assertEqual(result.status_code, 201, result.text)
        encoded, mime, _ = provider.call_args.args
        self.assertEqual(mime, "image/jpeg")
        self.assertEqual(Image.open(BytesIO(encoded)).size, (1440, 720))
        self.assertIn("prevention", result.json()["actions"])

    def test_garden_profiles_and_private_care_lifecycle(self):
        a = self.account(self.a, "garden-owner@example.com")
        b = self.account(self.b, "garden-other@example.com")
        plant = self.a.post("/api/plantas/identificar", files=photo(), headers=a).json()["id"]
        path = f"/api/jardim/{plant}"
        self.assertEqual(self.a.get("/api/jardim").status_code, 401)
        self.assertEqual(self.a.get("/api/jardim", headers=a).json()["plants"][0]["id"], plant)
        self.assertEqual(self.b.get("/api/jardim", headers=b).json()["plants"], [])
        form = {"nickname": "  Minha   samambaia  ", "location": "Varanda Hélice"}
        self.assertEqual(self.b.post(path + "/perfil", data=form, headers=b).status_code, 404)
        profile = self.a.post(path + "/perfil", data=form, headers=a)
        self.assertEqual(profile.json()["nickname"], "Minha samambaia")
        view = self.a.get("/api/jardim", params={"location":"varanda helice"}, headers=a).json()
        self.assertEqual([item["id"] for item in view["plants"]], [plant])
        self.assertEqual(self.b.get("/api/jardim", headers=b).json()["locations"], [])
        self.assertEqual(self.b.get(path, headers=b).status_code, 404)
        data = {"kind":"water", "due_on":"2026-11-25"}
        task = self.a.post(path + "/tarefas", data=data, headers=a)
        self.assertEqual(task.status_code, 201, task.text)
        task_id = task.json()["id"]
        self.assertEqual(self.a.post(path + "/tarefas", data=data, headers=a).json()["id"], task_id)
        self.assertEqual(self.b.post(path + "/tarefas", data=data, headers=b).status_code, 404)
        action = path + f"/tarefas/{task_id}"
        self.assertEqual(self.b.post(action + "/concluir", headers=b).status_code, 404)
        self.assertEqual(self.b.post(action + "/reagendar", data={"due_on":"2026-11-26"}, headers=b).status_code, 404)
        self.assertEqual(self.a.post(action + "/reagendar", data={"due_on":"2026-11-26"}, headers=a).json()["due_on"], "2026-11-26")
        self.assertTrue(self.a.post(action + "/concluir", headers=a).json()["completed"])
        self.assertTrue(self.a.post(action + "/concluir", headers=a).json()["completed"])
        self.assertEqual(self.a.get("/api/jardim", headers=a).json()["tasks"], [])
        self.assertEqual(self.a.get("/api/jardim", headers=a, params={"done":True}).json()["tasks"][0]["id"], task_id)
        self.assertEqual(self.a.get(f"/jardim/{plant}", headers={**a,"Accept-Language":"ar"}).status_code, 200)
        self.assertEqual(self.a.delete(f"/api/plantas/{plant}", headers=a).status_code, 204)
        self.assertEqual(self.a.get("/api/jardim", headers=a, params={"done":True}).json()["tasks"], [])

    def test_garden_prefills_health_review_without_creating_task(self):
        a = self.account(self.a, "garden-review@example.com")
        plant = self.a.post("/api/plantas/identificar", files=photo(), headers=a).json()["id"]
        with patch("plantia.services.health.analyze", return_value=Triage(
            status="possible", concern="high", signs=["spots"], findings=["fungal"]
        )):
            response = self.a.post(f"/api/plantas/{plant}/saude/avaliar", files={"photo":photo()["file"]}, headers=a)
        self.assertEqual(response.status_code, 201)
        review = response.json()["review_date"]
        self.assertIn(f"/jardim/{plant}?kind=review", self.a.get(f"/plantas/{plant}/saude", headers=a).text)
        view = self.a.get(f"/api/jardim/{plant}", params={"kind":"review","due_on":review}, headers=a).json()
        self.assertEqual(view["suggested_date"], review)
        self.assertEqual(view["selected_kind"], "review")
        self.assertEqual(view["tasks"], [])
        self.assertEqual(self.a.post(f"/api/jardim/{plant}/tarefas", data={"kind":"unknown","due_on":review}, headers=a).status_code, 422)

    def test_gemini_request_uses_selected_model_and_language(self):
        self.mock.stop()
        with patch.object(GeminiService, "_get_client") as client:
            model = client.return_value.models.generate_content
            model.return_value.text = '{"nombre_comun":"Farn"}'
            GeminiService.identificar(b"prepared", "image/jpeg", "German", already_prepared=True)
            self.assertEqual(model.call_args.kwargs["model"], "gemini-3.1-flash-lite")
            self.assertIn("in German", model.call_args.kwargs["contents"][0])


if __name__ == "__main__":
    unittest.main()
