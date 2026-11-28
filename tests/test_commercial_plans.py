"""Commercial plan transitions, enforcement and exact catalog defaults."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import text

import test_regression as fixture
from plantia import commercial
from plantia.services import ai_meter, stripe_billing


class CommercialPlans(unittest.TestCase):
    def setUp(self):
        self.api = TestClient(fixture.app, base_url="https://testserver")
        with commercial.transaction() as db:
            db.execute(text("DELETE FROM rate_windows"))

    def member(self, name):
        email = f"tiers-{name}@example.com"
        fixture.accounts.register(email, fixture.PASSWORD)
        token = fixture.accounts.login(email, fixture.PASSWORD)
        return fixture.accounts.account_for(token), {"Authorization": "Bearer " + token}

    def test_br_catalog_and_free_to_plus_to_premium_permissions(self):
        owner, headers = self.member("permissions")
        account = self.api.get("/api/assinatura", headers=headers).json()
        self.assertEqual(account["usage"]["remaining"], 3)
        self.assertEqual({p["plan"]: p["amount"] for p in account["prices"]}, {
            "plus_monthly": 1990, "plus_annual": 14990, "annual": 19990,
        })
        self.assertEqual(self.api.get("/api/assinatura?market=JP", headers=headers).json()["prices"], [])
        with patch.object(fixture.GeminiService, "identificar", return_value=fixture.IdentificacionGemini(
            nombre_comun="Fern", nombre_cientifico="Dryopteris filix-mas"
        )):
            ident = self.api.post("/api/plantas/identificar", files=fixture.photo(), headers=headers)
        self.assertEqual(ident.status_code, 200, ident.text)
        path = f"/api/plantas/{ident.json()['id']}/saude"
        web_path = path.removeprefix("/api")

        def assert_health_presentation(diagnosis, assistant):
            for locale in fixture.LANGUAGES:
                with self.subTest(locale=locale, diagnosis=diagnosis, assistant=assistant):
                    response = self.api.get(web_path, headers={**headers, "Accept-Language": locale})
                    self.assertEqual(response.status_code, 200)
                    messages = fixture.catalog(locale)
                    self.assertEqual(messages["health.diagnosis_unavailable_for_account"] in response.text, not diagnosis)
                    self.assertEqual(messages["health.assistant_unavailable_for_account"] in response.text, not assistant)
                    self.assertEqual(f'action="{web_path}/avaliar"' in response.text, diagnosis)
                    self.assertEqual(f'action="{web_path}/assistente"' in response.text, assistant)
                    self.assertNotIn(messages["commercial.disabled"], response.text)

        assert_health_presentation(diagnosis=False, assistant=False)
        upload = {"photo": fixture.photo()["file"]}
        question = {"question": "What should I do?"}
        with patch("plantia.services.health.analyze", return_value=fixture.Triage(
            status="possible", concern="high", signs=["spots"], findings=["fungal"]
        )) as diagnose, patch("plantia.services.health.assist", return_value=fixture.AssistantReply(
            status="guidance", actions=["inspect"]
        )) as assist:
            self.assertEqual(self.api.post(path + "/avaliar", files=upload, headers=headers).status_code, 403)
            self.assertEqual(self.api.post(path + "/assistente", data=question, headers=headers).status_code, 403)
            diagnose.assert_not_called()
            assist.assert_not_called()
            fixture.grant_fixture_subscription(owner, "plus_monthly")
            assert_health_presentation(diagnosis=True, assistant=False)
            self.assertEqual(self.api.post(path + "/avaliar", files=upload, headers=headers).status_code, 201)
            self.assertEqual(self.api.post(path + "/assistente", data=question, headers=headers).status_code, 403)
            fixture.grant_fixture_subscription(owner, "annual", checked_at=2)
            assert_health_presentation(diagnosis=True, assistant=True)
            self.assertEqual(self.api.post(path + "/assistente", data=question, headers=headers).status_code, 201)
            fixture.grant_fixture_subscription(owner, "plus_annual", checked_at=3)
            self.assertEqual(self.api.post(path + "/assistente", data=question, headers=headers).status_code, 403)
            assist.assert_called_once()
            fixture.grant_fixture_subscription(owner, "plus_annual", checked_at=4, period_end=1)
            self.assertEqual(self.api.post(path + "/avaliar", files=upload, headers=headers).status_code, 403)
        self.assertEqual(self.api.get(path, headers=headers).json()["benefits"], {
            "identify": True, "diagnosis": False, "assistant": False,
        })

    def test_exact_free_limit_is_enforced_and_web_text_covers_twelve_locales(self):
        owner, headers = self.member("free-limit")
        for locale in fixture.LANGUAGES:
            response = self.api.get("/assinatura", headers={**headers, "Accept-Language": locale})
            self.assertEqual(response.status_code, 200)
            self.assertIn(f'lang="{locale}"', response.text)
            self.assertIn(fixture.catalog(locale)["commercial.fair_title"], response.text)
        for _ in range(3):
            with ai_meter.measure(owner, "identify"):
                pass
        with self.assertRaises(HTTPException) as quota:
            with ai_meter.measure(owner, "identify"):
                self.fail("The fourth Free consultation must be rejected")
        self.assertEqual(quota.exception.detail, "commercial.quota")

    def test_monthly_reset_credits_and_premium_without_monthly_cap(self):
        owner, headers = self.member("month")
        admin, admin_headers = self.member("grant-admin")
        fixture.grant_fixture_subscription(owner, "plus_annual")
        with commercial.transaction() as db:
            db.execute(text("UPDATE accounts SET commercial_role='admin' WHERE id=:id"), {"id": admin})
            db.execute(text("""INSERT INTO ai_meter(account_id,feature,created_at,state)
                VALUES (:owner,'identify',:created,'success')"""),
                       [{"owner": owner, "created": commercial.month_start() + 1}] * 50)
        address = f"/admin/comercial/contas/{owner}/creditos"
        self.assertEqual(self.api.post(address, data={"quantity": 2}, headers=headers).status_code, 403)
        self.assertEqual(self.api.post(address, data={"quantity": 2}, headers=admin_headers,
                                       follow_redirects=False).status_code, 303)
        for expected in (1, 0):
            with ai_meter.measure(owner, "identify"):
                ai_meter.provider_attempt("gemini-3.1-flash-lite")
                ai_meter.provider_attempt("gemini-3.1-flash-lite")
                ai_meter.capture(SimpleNamespace(usage_metadata=SimpleNamespace(prompt_token_count=20)))
            self.assertEqual(self.api.get("/api/assinatura", headers=headers).json()["usage"]["credits"], expected)
        with self.assertRaises(HTTPException) as quota:
            with ai_meter.measure(owner, "identify"):
                self.fail("Quota must be enforced before execution")
        self.assertEqual(quota.exception.status_code, 429)
        with patch("plantia.commercial.month_start", return_value=4_000_000_000):
            self.assertEqual(self.api.get("/api/assinatura", headers=headers).json()["usage"]["remaining"], 50)
        for plan in ("monthly", "annual"):
            fixture.grant_fixture_subscription(owner, plan, checked_at=2)
            self.assertIsNone(self.api.get("/api/assinatura", headers=headers).json()["usage"]["limit"])
            with ai_meter.measure(owner, "identify"):
                with self.assertRaises(HTTPException) as concurrent:
                    with ai_meter.measure(owner, "assistant"):
                        self.fail("An overlapping Premium request must be rejected")
                self.assertEqual(concurrent.exception.detail, "commercial.concurrent")
        with commercial.transaction() as db:
            row = db.execute(text("""SELECT sum(provider_calls),sum(input_tokens)
                FROM ai_meter WHERE account_id=:owner AND model='gemini-3.1-flash-lite'"""),
                {"owner": owner}).one()
            self.assertEqual(tuple(row), (4, 40))
            self.assertEqual(db.execute(text("SELECT count(*) FROM commercial_audit WHERE actor=:id AND action='credits.grant'"),
                                        {"id": admin}).scalar_one(), 1)

    def test_plus_annual_stripe_recurring_metadata_and_entitlement(self):
        offer = {"plan": "plus_annual", "amount": 14990, "currency": "BRL"}
        product = {"unit_amount": 14990, "currency": "brl", "recurring": {"interval": "year", "interval_count": 1}}
        self.assertTrue(stripe_billing._same_price(product, offer))
        self.assertFalse(stripe_billing._same_price(product, {**offer, "plan": "plus_monthly"}))
        owner, headers = self.member("stripe-plus")
        with commercial.transaction() as db:
            commercial.put_price(db, owner, "BR", "plus_annual", "BRL", 14990, "price_fixturePlusAnnual")
            db.execute(text("INSERT INTO billing_customers VALUES (:owner,'stripe','cus_fixturePlus')"), {"owner": owner})
        from time import time
        def snapshot(period):
            return {"id": "sub_fixturePlus", "livemode": False, "customer": "cus_fixturePlus", "status": "active",
                    "items": {"data": [{"quantity": 1, "current_period_end": period,
                                       "price": {**product, "id": "price_fixturePlusAnnual"}}]}}
        now = int(time())
        for n, until in ((1, now + 3600), (2, now + 86400)):
            with patch.object(stripe_billing, "send", return_value=snapshot(until)):
                stripe_billing.webhook({"id": f"evt_fixturePlus{n}", "type": "customer.subscription.updated",
                                        "data": {"object": {"id": "sub_fixturePlus"}}})
            self.assertEqual(self.api.get("/api/assinatura", headers=headers).json()["usage"]["tier"], "plus")
        with commercial.transaction() as db:
            self.assertEqual(commercial.current_subscription(db, owner)["period_end"], now + 86400)

    def test_migration_preserves_legacy_price_subscription_and_data(self):
        owner, headers = self.member("migration")
        fixture.grant_fixture_subscription(owner, "annual")
        with commercial.transaction() as db:
            original = commercial.rules(db)
            legacy = original.model_dump(exclude={"plus_limit", "free_diagnosis", "free_assistant", "plus_diagnosis",
                "plus_assistant", "plus_credits_enabled", "plus_monthly_enabled", "plus_annual_enabled"})
            import json
            db.execute(text("UPDATE commercial_rules SET payload=:value WHERE id=1"),
                       {"value": json.dumps({**legacy, "free_limit": 50, "monthly_limit": 500, "annual_limit": 500})})
        commercial.init()
        commercial.init()
        self.assertEqual(self.api.get("/api/assinatura", headers=headers).json()["usage"]["tier"], "premium")
        with commercial.transaction() as db:
            self.assertEqual(commercial.rules(db).free_limit, 3)
            self.assertEqual(db.execute(text("SELECT count(*) FROM commercial_prices WHERE market='BR' AND enabled=1"))
                             .scalar_one(), 4)
