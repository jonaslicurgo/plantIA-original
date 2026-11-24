"""Evidence attribution, preventive safety and taxon identity tests."""

import os
import unittest
from unittest.mock import patch

import test_regression as fixture
from plantia.services import botanical_catalog, botanical_enrichment as evidence


def index_item(name, family):
    return {"id": "gbif-2000", "gbif": 2000, "name": name, "family": family,
            "source": "https://www.gbif.org/species/2000", "aliases": [], "lineage": [], "labels": {}}


class Evidence(unittest.TestCase):
    def test_five_species_have_the_expected_safety_evidence_in_all_locales(self):
        for locale in fixture.LANGUAGES:
            catalog = fixture.catalog(locale)
            for name, family in evidence.PRIORITIES.items():
                with self.subTest(locale=locale, species=name), patch(
                    "plantia.services.botanical_backbone.enrich", return_value={}
                ):
                    profile = botanical_catalog.profile(index_item(name, family), -1, locale, catalog.__getitem__)
                    fields = {item["key"]: item for group in profile["groups"] for item in group["items"]}
                    animal = fields["animal_toxicity"]
                    self.assertIsNotNone(animal["value"])
                    self.assertIn("ncsu.edu" if name.startswith("Ricinus") else "aspca.org", animal["source"]["url"])
                    if name != "Ocimum basilicum":
                        self.assertIsNotNone(fields["human_toxicity"]["value"])
                    if locale == "pt-BR" and name == "Monstera deliciosa":
                        self.assertEqual(fields["common_name"]["value"], "Costela-de-adão")
                        self.assertIn("oxalato", fields["human_toxicity"]["value"])
                        self.assertIn("Catalogue of Life", fields["common_name"]["source"]["label"])
                    if locale == "pt-BR" and name == "Ocimum basilicum":
                        self.assertIn("não tóxica", animal["value"])
                    if name in {"Monstera deliciosa", "Ricinus communis", "Nerium oleander"}:
                        self.assertIsNotNone(fields["toxic_parts"]["value"])
                        self.assertIsNone(fields["edible"]["value"])
                    self.assertTrue(profile["gap_notice"])

    def test_curated_aloe_preserves_nih_and_adds_pet_toxicity(self):
        tr = fixture.catalog("pt-BR").__getitem__
        result = botanical_catalog.profile(botanical_catalog.CATALOG["aloe-vera"], -1, "pt-BR", tr)
        fields = {item["key"]: item for group in result["groups"] for item in group["items"]}
        self.assertEqual(fields["animal_toxicity"]["source"]["label"], "ASPCA Poison Control")
        self.assertIn("nccih.nih.gov", fields["skin"]["source"]["url"])

    def test_wrong_family_or_species_never_receives_safety_facts(self):
        translate = fixture.catalog("en").__getitem__
        self.assertEqual(evidence.facts(index_item("Monstera deliciosa", "Rosaceae"), "en", translate), [])
        self.assertEqual(evidence.facts(index_item("Monstera adansonii", "Araceae"), "en", translate), [])

    def test_extension_extracts_only_exact_controlled_evidence(self):
        page = b'''<h1><em>Monstera deliciosa</em></h1><dl>
        <dt>Light:</dt><dd><span class="detail_display_attribute">Dappled Sunlight (canopy)</span></dd>
        <dt>Soil Drainage:</dt><dd><span class="detail_display_attribute">Good Drainage</span></dd>
        <dt>Poison Symptoms:</dt><dd><span class="detail_display_attribute">Untrusted text</span></dd></dl>'''
        with patch.object(evidence, "_download", return_value=page):
            self.assertEqual(evidence._extension("Monstera deliciosa", evidence.NC),
                             {"light": ["dappled"], "drainage": ["drainage_value"]})
            self.assertIsNone(evidence._extension("Monstera adansonii", evidence.NC))

    def test_kew_requires_accepted_species_family_and_wcvp_provider(self):
        identifier = "urn:lsid:ipni.org:names:87478-1"
        match = {"fqId": identifier, "name": "Monstera deliciosa", "family": "Araceae",
                 "rank": "Species", "kingdom": "Plantae", "accepted": True}
        detail = {**match, "taxonomicStatus": "Accepted", "source": "wcvp:129588",
                  "distribution": {"natives": [{"name": "Guatemala"}], "introduced": [{"name": "Bangladesh"}]}}
        with patch.object(evidence, "_json", side_effect=[{"results": [match]}, detail]):
            result = evidence._kew("Monstera deliciosa", "Araceae")
        self.assertEqual(result["natives"], ["Guatemala"])
        self.assertEqual(result["introduced"], ["Bangladesh"])
        with patch.object(evidence, "_json", return_value={"results": [{**match, "accepted": False}]}) as fetch:
            self.assertIsNone(evidence._kew("Monstera deliciosa", "Araceae"))
            fetch.assert_called_once()
        with patch.object(evidence, "_json", side_effect=[{"results": [match]}, {**detail, "source": "other"}]):
            self.assertIsNone(evidence._kew("Monstera deliciosa", "Araceae"))

    def test_persistent_cache_shared_between_languages(self):
        item = index_item("Monstera deliciosa", "Araceae")
        with patch.dict(os.environ, {"PLANET_BOTANICAL_ENRICHMENT": "1"}), patch.object(
            evidence, "_kew", return_value={"url": evidence.KEW, "natives": ["Guatemala"]}
        ) as kew, patch.object(evidence, "_extension", return_value={"light": ["dappled"]}) as extension:
            for locale in ("pt-BR", "en"):
                fields = dict((field, value) for field, value, _ in
                              evidence.facts(item, locale, fixture.catalog(locale).__getitem__))
                self.assertEqual(fields["origin"], "Guatemala")
                self.assertEqual(fields["light"], fixture.catalog(locale)["enrichment.dappled"])
            kew.assert_called_once()
            extension.assert_called_once()
