"""Stripe sandbox contract tests with mocked provider responses."""

import unittest
from time import time
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import text

import test_regression as fixture
from plantia import commercial
from plantia.services import ai_meter, stripe_billing


class PremiumIntroduction(unittest.TestCase):
    def test_checkout_and_subscription_lifecycle(self):
        email = "premium-intro-fixture@example.com"
        fixture.accounts.register(email, fixture.PASSWORD)
        token = fixture.accounts.login(email, fixture.PASSWORD)
        owner = fixture.accounts.account_for(token)
        headers = {"Authorization": f"Bearer {token}"}
        api = TestClient(fixture.app, base_url="https://testserver")
        provider_price = dict(id="price_introFixture", unit_amount=3990, currency="brl", active=True,
                              product="prod_introFixture", recurring={"interval": "month", "interval_count": 1})
        coupon = dict(id="introFixture", valid=True, livemode=False, amount_off=1000, currency="brl",
                      duration="repeating", duration_in_months=3, applies_to={"products": ["prod_introFixture"]})
        state = {}
        requests = []
        with commercial.transaction() as db:
            db.execute(text("DELETE FROM rate_windows"))
            db.execute(text("INSERT INTO billing_customers VALUES (:owner,'stripe','cus_introFixture')"),
                       {"owner": owner})
            old = db.execute(text("SELECT id FROM commercial_prices WHERE market='BR' AND plan='monthly' AND enabled=1")).scalar_one()
            commercial.put_price(db, 0, "BR", "monthly", "BRL", 3990, "price_introFixture")
            mapping = db.execute(text("SELECT id FROM commercial_prices WHERE stripe_price='price_introFixture'")).scalar_one()
            self.assertEqual(db.execute(text("SELECT amount FROM commercial_prices WHERE id=:id"), {"id": old}).scalar_one(), 2990)
        self.addCleanup(self.remove_offer, mapping, old)

        def send(path, data=None, idempotency=None):
            if path == "/prices/price_introFixture":
                return provider_price
            if path.startswith("/coupons/introFixture?"):
                return coupon
            if path == "/checkout/sessions":
                requests.append((data, idempotency))
                return {"url": "https://checkout.stripe.com/c/pay/test"}
            self.assertEqual(path, "/subscriptions/" + state["id"])
            return state

        def checkout(accept=False):
            return api.post("/assinatura/checkout", headers=headers, follow_redirects=False,
                            data={"price": mapping, "accept_intro": str(accept).lower()})

        def event(index, kind, status, period, *, subscription="sub_introFixture", cancel=False):
            state.update(id=subscription, status=status, customer="cus_introFixture", livemode=False,
                         cancel_at_period_end=cancel,
                         items={"data": [{"price": provider_price, "quantity": 1, "current_period_end": period}]})
            envelope = {"id": subscription}
            if kind.startswith("invoice."):
                envelope = {"id": f"in_fixture{index}",
                            "parent": {"subscription_details": {"subscription": subscription}}}
            stripe_billing.webhook({"id": f"evt_introFixture{index}", "type": kind,
                                   "data": {"object": envelope}})

        def plan():
            return api.get("/api/assinatura", headers=headers).json()["usage"]["plan"]

        with patch.dict("os.environ", {"PLANET_STRIPE_PREMIUM_INTRO_COUPON": "introFixture"}), \
             patch.object(stripe_billing, "send", side_effect=send), patch.object(stripe_billing, "ready", return_value=True):
            for locale in fixture.LANGUAGES:
                page = api.get("/assinatura", headers={**headers, "Accept-Language": locale})
                self.assertIn("R$ 29,90", page.text)
                self.assertIn("R$ 39,90", page.text)
                for key in ("intro_period", "intro_renewal", "intro_accept"):
                    self.assertIn(fixture.catalog(locale)["commercial." + key], page.text)
            self.assertEqual(checkout().status_code, 409)
            coupon["duration_in_months"] = 2
            self.assertEqual(checkout(True).status_code, 503)
            self.assertFalse(requests)
            coupon["duration_in_months"] = 3
            self.assertEqual(checkout(True).status_code, 303)
            self.assertEqual(requests[0][0]["discounts[0][coupon]"], "introFixture")
            self.assertEqual(requests[0][0]["line_items[0][price]"], "price_introFixture")
            self.assertNotIn("allow_promotion_codes", requests[0][0])
            now = int(time())
            event(0, "customer.subscription.created", "incomplete", now + 60)
            event(1, "invoice.payment_failed", "incomplete", now + 60)
            self.assertEqual(plan(), "free")
            for cycle in range(1, 5):
                # Billing is performed by Stripe. Exercise four successive verified renewal snapshots.
                event(cycle + 1, "invoice.paid", "active", now + cycle * 30 * 86400)
                self.assertEqual(plan(), "monthly")
                with commercial.transaction() as db:
                    self.assertIsNone(commercial.allowance(db, owner)["limit"])
                self.assertTrue(all(ai_meter.available_features(owner).values()))
            event(6, "invoice.payment_failed", "past_due", now + 100)
            self.assertEqual(plan(), "free")
            self.assertEqual(checkout(True).status_code, 409)
            event(7, "invoice.paid", "active", now + 100, cancel=True)
            self.assertEqual(plan(), "monthly")
            self.assertEqual(checkout(True).status_code, 409)
            event(8, "customer.subscription.deleted", "canceled", now - 1)
            self.assertEqual(plan(), "free")
            self.assertEqual(checkout(True).status_code, 303)
            self.assertEqual(requests[-1][0]["discounts[0][coupon]"], "introFixture")
            self.assertNotEqual(requests[0][1], requests[-1][1])

    @staticmethod
    def remove_offer(mapping, old):
        with commercial.transaction() as db:
            db.execute(text("DELETE FROM checkout_pending WHERE price_id=:id"), {"id": mapping})
            db.execute(text("DELETE FROM commercial_prices WHERE id=:id"), {"id": mapping})
            db.execute(text("UPDATE commercial_prices SET enabled=1 WHERE id=:id"), {"id": old})
