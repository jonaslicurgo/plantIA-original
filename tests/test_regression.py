"""Run only through the isolated test launcher documented in CHANGELOG.md."""

from io import BytesIO
from pathlib import Path
import os
import tempfile
import sqlite3
import subprocess
import sys
import unittest
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
from plantia.i18n import LANGUAGES, catalog
from plantia.schemas.planta import IdentificacionGemini
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
        self.mock = patch.object(GeminiService, "identificar", return_value=IdentificacionGemini(nombre_comun="Test fern"))
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
                self.assertEqual(db.execute("SELECT id, nombre_comun, owner_id FROM plantas").fetchall(),
                                 [(7, "Legacy", None)])
                self.assertEqual(db.execute("SELECT count(*) FROM accounts").fetchone()[0], 0)

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
