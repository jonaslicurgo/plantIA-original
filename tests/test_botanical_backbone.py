"""Indexed taxonomy, licenses, refresh rejection and grounded Gemini highlight coverage."""

import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import test_regression as fixture
from plantia.services import botanical_backbone as backbone, botanical_catalog as library
from scripts.import_botanical_backbone import build


def record(key, parent, rank, name, status="ACCEPTED", kingdom="6"):
    row = [r"\N"] * 30
    for index, value in {0: key, 1: parent, 4: status, 5: rank, 10: kingdom,
                         14: "1200", 18: name + " L.", 19: name}.items():
        row[index] = str(value)
    return "\t".join(row) + "\n"


class BotanicalBackbone(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        path = Path(directory) / "botanical.sqlite"
        rows = [record(1200, 6, "FAMILY", "Fagaceae"), record(1250, 1200, "GENUS", "Quercus"),
                record(1251, 1250, "SPECIES", "Quercus robur"),
                record(1252, 1251, "SPECIES", "Quercus pedunculata", "SYNONYM"),
                record(1253, 1250, "SPECIES", "Felis ficta", kingdom="1"),
                record(1254, 1250, "SPECIES", "Aloe vera")]
        self.assertEqual(build(rows, path, 1), (1, 1))
        self.enterContext(patch.dict(os.environ, {"PLANET_BOTANICAL_INDEX": str(path)}))
        self.api = TestClient(fixture.app, base_url="https://testserver")

    def login(self, label):
        email = f"backbone-{label}@example.com"
        fixture.accounts.register(email, fixture.PASSWORD)
        token = fixture.accounts.login(email, fixture.PASSWORD)
        return fixture.accounts.account_for(token), {"Authorization": f"Bearer {token}"}

    def test_search_synonym_profiles_and_favorites(self):
        _, auth = self.login("search")
        base = "/api/biblioteca"
        self.assertEqual(self.api.get(base, headers=auth).json()["total"], len(library.CATALOG) + 1)
        self.assertEqual(self.api.get(base, params={"q":"Quercus pedunculata"}, headers=auth).json()["items"][0]["id"], "gbif-1251")
        with patch.object(backbone, "_request", return_value={"count": 1, "results": [
            {"key": 1251, "vernacularNames": [{"vernacularName": "English oak", "language": "eng"}]}
        ]}) as request:
            for _ in range(2):
                self.assertEqual(self.api.get(base, params={"q":"English oak"}, headers=auth)
                                 .json()["items"][0]["common_name"], "English oak")
            request.assert_called_once()
        with patch.object(backbone, "enrich", return_value={"countries": ["BR", "GB"]}):
            profile = self.api.get(base + "/gbif-1251", headers=auth).json()
        self.assertEqual(profile["kind"], "taxonomy")
        self.assertEqual(profile["license"], backbone.LICENSE)
        fields = {item["key"]: item for group in profile["groups"] for item in group["items"]}
        self.assertEqual(fields["family"]["value"], "Fagaceae")
        self.assertIn("BR", fields["observations"]["value"])
        self.assertIsNone(fields["human_toxicity"]["value"])
        self.assertEqual(self.api.patch(base + "/gbif-1251/favorito", json={"favorite": True}, headers=auth).status_code, 200)
        self.assertEqual(self.api.get(base + "?favorite=true", headers=auth).json()["total"], 1)
        self.assertEqual(self.api.get(base + "/gbif-1253", headers=auth).status_code, 404)

    def test_license_is_per_media_and_requires_attribution(self):
        example = {"identifier": "https://upload.wikimedia.org/specimen.jpg", "type": "StillImage",
                   "license": "https://creativecommons.org/licenses/by/4.0/", "creator": "Example Author"}
        def result(media):
            return backbone.licensed_photo({"results": [{"key": 123, "license": example["license"], "media": [media]}]})
        self.assertEqual(result(example)["author"], "Example Author")
        for change in ({"license": None}, {"license": "https://creativecommons.org/licenses/by-nc/4.0/"},
                       {"creator": ""}, {"identifier": "http://example.org/image.jpg"}, {"type": "Sound"}, {"identifier": "https://example.org/specimen.jpg"}):
            self.assertIsNone(result({**example, **change}))

    def test_gemini_highlights_are_sourced_cached_and_plan_gated(self):
        owner, auth = self.login("premium")
        _, free = self.login("free")
        fixture.grant_fixture_subscription(owner, "monthly")
        path = "/api/biblioteca/ocimum-basilicum/resumo"
        with patch.object(fixture.GeminiService, "_get_client") as client:
            generate = client.return_value.models.generate_content
            generate.return_value = SimpleNamespace(text='{"fields":["family","injected","medicinal","family"]}')
            self.assertEqual(self.api.post(path, headers=free).status_code, 403)
            for _ in range(2):
                response = self.api.post(path, headers=auth)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual([field["key"] for field in response.json()["items"]], ["family"])
            generate.assert_called_once()

    def test_below_minimum_snapshot_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "Import rejected"):
                build([record(11, 1, "SPECIES", "Example plant")], Path(directory) / "example.sqlite", 100000)
