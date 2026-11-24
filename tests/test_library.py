"""Global catalog journeys. Botanical data and licensed images are local fixtures."""
from pathlib import Path
import unittest
import re
from unittest.mock import patch
from urllib.parse import urlsplit

from fastapi.testclient import TestClient
from sqlalchemy import text

import test_regression as fixture
from plantia.services import botanical_catalog as library


class BotanicalLibrary(unittest.TestCase):
    def setUp(self):
        with fixture.get_engine().begin() as db:
            db.execute(text("DELETE FROM rate_windows"))
        self.client = TestClient(fixture.app, base_url="https://testserver")

    def login(self, email):
        fixture.accounts.register(email, fixture.PASSWORD)
        token = fixture.accounts.login(email, fixture.PASSWORD)
        return {"Authorization": f"Bearer {token}"}

    def test_catalog_is_independent_from_plant_history_and_searches_names(self):
        path = "/api/biblioteca"
        self.assertEqual(self.client.get(path).status_code, 401)
        owner = self.login("library-fresh@example.com")
        self.assertEqual(self.client.get("/api/enciclopedia", headers=owner).json()["total"], 0)
        result = self.client.get(path, headers=owner).json()
        self.assertEqual(result["total"], len(library.CATALOG))
        self.assertGreater(result["total"], 7)
        second = self.client.get(path, params={"page": 2}, headers=owner).json()
        self.assertEqual(len({row["id"] for row in result["items"] + second["items"]}), result["total"])
        for name, species in (("manjericao", "ocimum-basilicum"), ("ocimum basilicum", "ocimum-basilicum"),
                              ("Rosmarinus officinalis", "salvia-rosmarinus")):
            result = self.client.get(path, params={"q": name}, headers=owner).json()
            self.assertEqual([row["id"] for row in result["items"]], [species])
        for category in ("tree", "flower", "fruit", "herb", "ornamental", "edible", "panc", "toxic",
                         "medicinal", "cosmetics", "skin", "hair", "seasoning", "cactus", "succulent"):
            with self.subTest(category=category):
                result = self.client.get(path, params={"category": category}, headers=owner).json()
                self.assertGreater(result["total"], 0)
        self.assertEqual(self.client.get(path, params={"category": "wrong"}, headers=owner).status_code, 400)
        web = self.client.get("/enciclopedia", headers=owner)
        self.assertEqual(web.status_code, 200)
        self.assertIn("/enciclopedia/especies/", web.text)
        self.assertNotIn("/enciclopedia/especies/", self.client.get("/enciclopedia/pessoal", headers=owner).text)

    def test_favorites_are_private_and_deleted_with_account(self):
        owner = self.login("library-save@example.com")
        other = self.login("library-other@example.com")
        path = "/api/biblioteca/epipremnum-aureum"
        for _ in range(2):
            self.assertTrue(self.client.patch(path + "/favorito", json={"favorite": True}, headers=owner).json()["favorite"])
        self.assertTrue(self.client.get(path, headers=owner).json()["favorite"])
        self.assertFalse(self.client.get(path, headers=other).json()["favorite"])
        self.assertEqual(self.client.get("/api/biblioteca?favorite=true", headers=owner).json()["total"], 1)
        self.assertEqual(self.client.get("/api/biblioteca?favorite=true", headers=other).json()["total"], 0)
        self.assertEqual(self.client.get("/api/biblioteca/not-a-species", headers=owner).status_code, 404)
        account_id = fixture.accounts.account_for(owner["Authorization"].split()[1])
        self.assertEqual(self.client.post("/api/auth/delete", data={
            "password": fixture.PASSWORD, "confirm": True,
        }, headers=owner).status_code, 200)
        self.assertEqual(library.favorite_ids(account_id), set())

    def test_evidence_i18n_and_local_photo_attribution(self):
        owner = self.login("library-evidence@example.com")
        for locale in fixture.LANGUAGES:
            tr = fixture.catalog(locale)
            for item in library.CATALOG.values():
                result = library.profile(item, -1, locale, lambda key: tr[key])
                fields = {fact["key"]: fact for group in result["groups"] for fact in group["items"]}
                self.assertIsNotNone(fields["scientific_name"]["source"])
                photo = result["photo"]
                if photo:
                    self.assertTrue(photo["author"])
                    self.assertEqual(urlsplit(photo["source"]).hostname, "commons.wikimedia.org")
                    self.assertEqual(urlsplit(photo["license_url"]).hostname, "creativecommons.org")
                    self.assertTrue((Path("plantia") / photo["url"].lstrip("/")).is_file())
        path = "/enciclopedia/especies/epipremnum-aureum"
        web = self.client.get(path, headers={**owner, "Accept-Language": "ar"})
        self.assertIn('dir="rtl"', web.text)
        self.assertIn("https://creativecommons.org/", web.text)
        self.assertIn("/static/botany/", web.text)
        result = self.client.get("/api/biblioteca/nerium-oleander", headers=owner).json()
        facts = {fact["key"]: fact for group in result["groups"] for fact in group["items"]}
        self.assertEqual(facts["animal_toxicity"]["source"]["label"], "ASPCA Poison Control")
        self.assertIsNotNone(facts["human_toxicity"]["source"])
        self.assertIsNone(facts["medicinal"]["value"])

    def test_twenty_species_profiles_preserve_navigation_and_evidence(self):
        curated = (
            "lavandula-angustifolia", "epipremnum-aureum", "aloe-vera", "lantana-camara",
            "mentha-spicata", "portulaca-oleracea", "dionaea-muscipula", "helianthus-annuus",
            "ocimum-basilicum", "salvia-rosmarinus", "thymus-vulgaris", "salvia-officinalis",
            "malus-domestica", "citrus-limon", "ficus-carica", "digitalis-purpurea", "nerium-oleander",
        )
        indexed = {
            "gbif-2868241": ("Monstera deliciosa", "Araceae"),
            "gbif-5380041": ("Ricinus communis", "Euphorbiaceae"),
            "gbif-2878688": ("Quercus robur", "Fagaceae"),
        }
        def lookup(key):
            if key not in indexed:
                return None
            name, family = indexed[key]
            return {"id": key, "name": name, "family": family, "gbif": int(key.split("-")[1]),
                    "labels": {}, "aliases": [], "lineage": ["Plantae"],
                    "source": "https://www.gbif.org/species/" + key.split("-")[1]}
        owner = self.login("library-profiles@example.com")
        with patch.object(library.backbone, "lookup", side_effect=lookup), patch.object(
            library.backbone, "enrich", return_value={}
        ):
            for species in (*curated, *indexed):
                with self.subTest(species=species):
                    for locale, direction in (("pt-BR", "ltr"), ("ar", "rtl")):
                        response = self.client.get(f"/enciclopedia/especies/{species}",
                                                   headers={**owner, "Accept-Language": locale})
                        self.assertEqual(response.status_code, 200)
                        html = response.text
                        self.assertIn(f'dir="{direction}"', html)
                        self.assertIn('class="species-identity"', html)
                        self.assertEqual(html.count('id="species-risks"'), 1)
                        self.assertIn(f'/enciclopedia/especies/{species}/favorito', html)
                        self.assertTrue(all(f'id="{target}"' in html for target in
                                            re.findall(r'href="#(species-[a-z]+)"', html)))
                        self.assertEqual(html.count(fixture.catalog(locale)["enrichment.gap_notice"]), 1)
                        if species == "gbif-2868241" and locale == "pt-BR":
                            self.assertIn("<h1>Costela-de-adão</h1>", html)
                            self.assertIn("oxalato de cálcio", html)
                            self.assertIn("aspca.org", html)
                        if species == "epipremnum-aureum":
                            self.assertIn("creativecommons.org", html)
