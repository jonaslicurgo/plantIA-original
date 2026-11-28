"""Test the Stripe mode boundary without a Stripe account or real credentials."""

import hashlib
import hmac
import json
import os
from time import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

import test_regression as fixture
from plantia import commercial
from plantia.services import stripe_billing as stripe


LIVE = {
    "PLANET_STRIPE_MODE": "live",
    "PLANET_DEPLOYMENT": "production",
    "RAILWAY_ENVIRONMENT_NAME": "production",
    "PLANET_STRIPE_LIVE_ENABLED": "1",
    "PLANET_STRIPE_LIVE_KEY": "sk_live_fixture",
    "PLANET_STRIPE_LIVE_WEBHOOK_SECRET": "whsec_live_fixture",
}
TEST = {
    "PLANET_STRIPE_MODE": "test",
    "PLANET_DEPLOYMENT": "staging",
    "RAILWAY_ENVIRONMENT_NAME": "staging",
    "PLANET_STRIPE_TEST_KEY": "sk_test_fixture",
    "PLANET_STRIPE_TEST_WEBHOOK_SECRET": "whsec_test_fixture",
}


def signature(body, secret):
    stamp = str(int(time()))
    digest = hmac.new(secret.encode(), stamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    return f"t={stamp},v1={digest}"


class StripeModes(unittest.TestCase):
    def test_endpoint_secret_event_mode_and_live_gate(self):
        api = TestClient(fixture.app, base_url="https://testserver")
        paths = {"test": "/api/stripe/webhook", "live": "/api/stripe/webhook/live"}
        for config, expected, other in [(TEST, "test", "live"), (LIVE, "live", "test")]:
            with self.subTest(expected=expected), patch.dict(os.environ, {**TEST, **config}, clear=True):
                def post(path, live, secret):
                    body = json.dumps({"id": "evt_modeFixture", "type": "ignored", "livemode": live}).encode()
                    return api.post(path, content=body, headers={"Stripe-Signature": signature(body, secret)})

                with patch.object(stripe, "webhook") as handler:
                    self.assertTrue(stripe.ready())
                    self.assertEqual(post(paths[expected], expected == "live", f"whsec_{expected}_fixture").status_code, 200)
                    self.assertEqual(post(paths[expected], expected == "live", f"whsec_{other}_fixture").status_code, 400)
                    self.assertEqual(post(paths[expected], other == "live", f"whsec_{expected}_fixture").status_code, 400)
                    self.assertEqual(post(paths[other], other == "live", f"whsec_{other}_fixture").status_code, 404)
                    handler.assert_called_once()

        for override in ({"PLANET_STRIPE_LIVE_ENABLED": "0"}, {"PLANET_DEPLOYMENT": "staging"},
                         {"RAILWAY_ENVIRONMENT_NAME": "staging"}, {"PLANET_STRIPE_LIVE_KEY": "sk_test_fixture"}):
            with self.subTest(override=override), patch.dict(os.environ, {**LIVE, **override}, clear=True):
                self.assertFalse(stripe.ready())

    def test_catalog_database_cannot_be_switched_or_reused(self):
        for mode, config in (("test", TEST), ("live", LIVE)):
            db_engine = create_engine("sqlite://")
            with db_engine.begin() as db:
                db.execute(text("CREATE TABLE accounts (id INTEGER PRIMARY KEY)"))
            try:
                with patch.object(commercial, "get_engine", return_value=db_engine), patch.dict(os.environ, config, clear=True):
                    commercial.init()
                    with db_engine.connect() as db:
                        self.assertEqual(db.execute(text("SELECT mode FROM stripe_database_mode")).scalar_one(), mode)
                    other = LIVE if mode == "test" else TEST
                    with patch.dict(os.environ, other, clear=True), self.assertRaisesRegex(RuntimeError, "different mode"):
                        commercial.init()
            finally:
                db_engine.dispose()

    def test_plus_checkout_and_signed_webhook_lifecycle(self):
        email = "stripe-modes-plus@example.com"
        fixture.accounts.register(email, fixture.PASSWORD)
        token = fixture.accounts.login(email, fixture.PASSWORD)
        owner = fixture.accounts.account_for(token)
        headers = {"Authorization": f"Bearer {token}"}
        api = TestClient(fixture.app, base_url="https://testserver")
        offer = {"active": True, "livemode": False, "id": "price_modesPlus", "currency": "brl",
                 "unit_amount": 1990, "recurring": {"interval": "month", "interval_count": 1}}
        with commercial.transaction() as db:
            db.execute(text("DELETE FROM rate_windows"))
            commercial.put_price(db, owner, "BR", "plus_monthly", "BRL", 1990, offer["id"])
            price = db.execute(text("SELECT id FROM commercial_prices WHERE stripe_price=:price"),
                               {"price": offer["id"]}).scalar_one()

        now = int(time())
        snapshot = {"id": "sub_modesPlus", "customer": "cus_modesPlus", "livemode": False,
                    "items": {"data": [{"price": offer, "quantity": 1}]}}

        def provider(path, data=None, idempotency=None):
            if path == "/prices/" + offer["id"]:
                return offer
            if path == "/customers":
                return {"id": snapshot["customer"], "livemode": False}
            if path == "/checkout/sessions":
                self.assertEqual(data["line_items[0][price]"], offer["id"])
                self.assertNotIn("discounts[0][coupon]", data)
                return {"url": "https://checkout.stripe.com/c/pay/test", "livemode": False}
            self.assertEqual(path, "/subscriptions/" + snapshot["id"])
            return snapshot

        with patch.dict(os.environ, TEST), patch.object(stripe, "send", side_effect=provider):
            response = api.post("/assinatura/checkout", data={"price": price}, headers=headers, follow_redirects=False)
            self.assertEqual(response.status_code, 303, response.text)
            stages = (
                ("invoice.payment_failed", "incomplete", now + 100, "free"),
                ("invoice.paid", "active", now + 100, "plus"),
                ("invoice.paid", "active", now + 200, "plus"),
                ("invoice.payment_failed", "past_due", now + 200, "free"),
                ("invoice.paid", "active", now + 300, "plus"),
                ("customer.subscription.updated", "active", now + 300, "plus"),
                ("customer.subscription.deleted", "canceled", now - 1, "free"),
            )
            for i, (kind, status, end, expected) in enumerate(stages):
                with self.subTest(kind=kind, status=status):
                    snapshot.update(status=status, cancel_at_period_end=i == 5)
                    snapshot["items"]["data"][0]["current_period_end"] = end
                    obj = {"parent": {"subscription_details": {"subscription": snapshot["id"]}}}
                    if not kind.startswith("invoice."):
                        obj = {"id": snapshot["id"]}
                    body = json.dumps({"type": kind, "id": f"evt_modesPlus{i}", "livemode": False,
                                       "data": {"object": obj}}).encode()
                    response = api.post("/api/stripe/webhook", content=body,
                                        headers={"Stripe-Signature": signature(body, TEST["PLANET_STRIPE_TEST_WEBHOOK_SECRET"])})
                    self.assertEqual(response.status_code, 200, response.text)
                    account = api.get("/api/assinatura", headers=headers).json()
                    self.assertEqual(account["usage"]["tier"], expected)
                    self.assertEqual(account["subscription"]["cancel_pending"], i == 5)
