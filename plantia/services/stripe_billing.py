"""Stripe test-mode adapter. No live API key can pass this boundary."""

import hashlib
import hmac
import json
import os
import re
from threading import Lock
from time import time, time_ns
from urllib.error import URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import uuid4

from sqlalchemy import text

from plantia.commercial import SubscriptionSnapshot, apply_subscription, current_subscription, entitled, rules, transaction
from plantia.database import get_engine

INVOICE_EVENTS = {"invoice.paid", "invoice.payment_failed"}
EVENTS = INVOICE_EVENTS | {
    "customer.subscription.created", "customer.subscription.updated", "customer.subscription.deleted",
    "customer.subscription.paused", "customer.subscription.resumed",
}
BLOCK_CHECKOUT = ("unmapped", "active", "trialing", "past_due", "unpaid", "incomplete", "paused")
LOCKS = tuple(Lock() for _ in range(32))


class BillingError(Exception):
    pass


class BillingConflict(BillingError):
    pass


class InvalidEvent(BillingError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


CLIENT = build_opener(NoRedirect())


def ready():
    return bool(re.fullmatch(r"(?:sk|rk)_test_[A-Za-z0-9]+", os.getenv("PLANET_STRIPE_KEY", ""))
                and os.getenv("PLANET_STRIPE_WEBHOOK_SECRET", "").startswith("whsec_"))


def send(path, data=None, idempotency=None):
    if not ready():
        raise BillingError
    headers = {"Authorization": "Bearer " + os.environ["PLANET_STRIPE_KEY"],
               "Stripe-Version": "2025-03-31.basil"}
    payload = None
    if data is not None:
        payload = urlencode(data).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if idempotency:
        headers["Idempotency-Key"] = idempotency
    try:
        with CLIENT.open(Request("https://api.stripe.com/v1" + path, headers=headers, data=payload), timeout=8) as res:
            result = json.loads(res.read(1024 * 1024))
    except (URLError, OSError, ValueError) as exc:
        raise BillingError from exc
    if not isinstance(result, dict) or result.get("livemode") is True:
        raise BillingError
    return result


def origin():
    url = os.getenv("PLANET_PUBLIC_ORIGIN", "").rstrip("/")
    parsed = urlsplit(url)
    if (parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"})) or (
        not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment
    ):
        raise BillingError
    return url


def redirect_url(result, host):
    url = result.get("url", "")
    parsed = urlsplit(url) if isinstance(url, str) else None
    if not parsed or parsed.scheme != "https" or parsed.netloc != host:
        raise BillingError
    return url


def account_customer(owner):
    with get_engine().connect() as db:
        return db.execute(text("SELECT external_id FROM billing_customers WHERE account_id=:owner AND provider='stripe'"),
                          {"owner": owner}).scalar()


def customer(owner):
    existing = account_customer(owner)
    if existing:
        return existing
    with get_engine().connect() as db:
        namespace = db.execute(text("SELECT namespace FROM commercial_installation WHERE id=1")).scalar_one()
    result = send("/customers", {"metadata[planet_account]": owner}, f"planet-test-customer-{namespace}-{owner}")
    identifier = result.get("id", "")
    if not re.fullmatch(r"cus_[A-Za-z0-9]+", identifier):
        raise BillingError
    with transaction() as db:
        db.execute(text("INSERT OR IGNORE INTO billing_customers VALUES (:owner,'stripe',:id)"),
                   {"owner": owner, "id": identifier})
    result = account_customer(owner)
    if not result:
        raise BillingError
    return result


def _same_price(provider_price, local_price):
    recurring = provider_price.get("recurring") or {}
    return (
        provider_price.get("unit_amount") == local_price["amount"]
        and provider_price.get("currency") == local_price["currency"].lower()
        and recurring.get("interval") == ("year" if local_price["plan"] in {"annual", "plus_annual"} else "month")
        and recurring.get("interval_count") == 1
        and provider_price.get("livemode") is not True
    )


def premium_intro(price):
    return (price["market"], price["plan"], price["currency"], price["amount"]) == (
        "BR", "monthly", "BRL", 3990,
    )


def premium_intro_coupon():
    coupon_id = os.getenv("PLANET_STRIPE_PREMIUM_INTRO_COUPON", "")
    return coupon_id if re.fullmatch(r"[A-Za-z0-9_-]{1,80}", coupon_id) else None


def _check_intro_coupon(coupon_id, product):
    coupon = send("/coupons/" + coupon_id + "?expand%5B%5D=applies_to")
    if (
        coupon.get("id") != coupon_id or coupon.get("livemode") is not False
        or coupon.get("valid") is not True or coupon.get("amount_off") != 1000
        or coupon.get("currency") != "brl" or coupon.get("duration") != "repeating"
        or coupon.get("duration_in_months") != 3 or not product
        or (coupon.get("applies_to") or {}).get("products") != [product]
        or coupon.get("max_redemptions") is not None or coupon.get("redeem_by") is not None
    ):
        raise BillingError


def checkout(owner, price_id, accept_intro=False):
    public = origin()
    with LOCKS[owner % len(LOCKS)]:
        now = int(time())
        with transaction() as db:
            sub = current_subscription(db, owner)
            if entitled(sub) or (sub and sub["status"] in BLOCK_CHECKOUT):
                raise BillingConflict
            price = db.execute(text("SELECT * FROM commercial_prices WHERE id=:id AND enabled=1"),
                               {"id": price_id}).mappings().first()
            if not price or not price["stripe_price"] or not getattr(rules(db), price["plan"] + "_enabled"):
                raise BillingError
            intro = premium_intro(price)
            coupon_id = premium_intro_coupon() if intro else None
            if intro and not accept_intro:
                raise BillingConflict
            if intro and not coupon_id:
                raise BillingError
            pending = db.execute(text("SELECT * FROM checkout_pending WHERE account_id=:owner AND expires>:now"),
                                 {"owner": owner, "now": now}).mappings().first()
            if pending and pending["price_id"] != price_id:
                raise BillingConflict
            if pending and pending["url"]:
                return redirect_url(pending, "checkout.stripe.com")
            if pending:
                request_key, expires = pending["request_key"], pending["expires"]
            else:
                request_key, expires = f"planet-test-checkout-{uuid4().hex}", now + 3600
                db.execute(text("""INSERT INTO checkout_pending VALUES (:owner,:price,:key,:expires,NULL)
                    ON CONFLICT(account_id) DO UPDATE SET price_id=excluded.price_id,
                    request_key=excluded.request_key, expires=excluded.expires, url=NULL"""),
                           {"owner": owner, "price": price_id, "key": request_key, "expires": expires})
        configured = send("/prices/" + price["stripe_price"])
        if not configured.get("active") or not _same_price(configured, price):
            raise BillingError
        params = {
            "mode": "subscription", "customer": customer(owner), "expires_at": expires,
            "billing_address_collection": "required", "line_items[0][price]": price["stripe_price"],
            "line_items[0][quantity]": 1, "success_url": public + "/assinatura",
            "cancel_url": public + "/assinatura",
        }
        if intro:
            _check_intro_coupon(coupon_id, configured.get("product"))
            params["discounts[0][coupon]"] = coupon_id
            params["subscription_data[metadata][planet_offer]"] = "br-premium-monthly-2990x3-3990-v1"
        result = send("/checkout/sessions", params, request_key)
        url = redirect_url(result, "checkout.stripe.com")
        with transaction() as db:
            db.execute(text("UPDATE checkout_pending SET url=:url WHERE account_id=:owner AND request_key=:key"),
                       {"url": url, "owner": owner, "key": request_key})
        return url


def portal(owner):
    identifier = account_customer(owner)
    if not identifier:
        raise BillingError
    result = send("/billing_portal/sessions", {"customer": identifier, "return_url": origin() + "/assinatura"})
    return redirect_url(result, "billing.stripe.com")


def verify(body, header):
    if not ready():
        raise BillingError
    fields = [part.strip().split("=", 1) for part in header.split(",") if "=" in part]
    stamps = [value for key, value in fields if key == "t"]
    if len(stamps) != 1 or not re.fullmatch(r"[0-9]{1,12}", stamps[0]):
        raise InvalidEvent
    if abs(int(stamps[0]) - int(time())) > 300:
        raise InvalidEvent
    digest = hmac.new(os.environ["PLANET_STRIPE_WEBHOOK_SECRET"].encode(),
                      stamps[0].encode() + b"." + body, hashlib.sha256).hexdigest()
    if not any(key == "v1" and re.fullmatch("[a-f0-9]{64}", sig) and hmac.compare_digest(sig, digest)
               for key, sig in fields):
        raise InvalidEvent
    try:
        event = json.loads(body)
    except (UnicodeError, ValueError) as exc:
        raise InvalidEvent from exc
    if not isinstance(event, dict) or event.get("livemode") is not False:
        raise InvalidEvent
    if not isinstance(event.get("id"), str) or not re.fullmatch(r"evt_[A-Za-z0-9]+", event["id"]):
        raise InvalidEvent
    return event


def webhook(event):
    kind = event.get("type")
    if not isinstance(kind, str) or kind not in EVENTS:
        return
    try:
        obj = event["data"]["object"]
        if kind in INVOICE_EVENTS:
            identifier = ((obj.get("parent") or {}).get("subscription_details") or {}).get("subscription")
            identifier = identifier or obj.get("subscription")
            if identifier is None:
                return  # A standalone invoice does not change subscription access.
        else:
            identifier = obj["id"]
        if not isinstance(identifier, str) or not re.fullmatch(r"sub_[A-Za-z0-9]+", identifier):
            raise InvalidEvent
    except (AttributeError, KeyError, TypeError) as exc:
        raise InvalidEvent from exc
    with get_engine().connect() as db:
        if _seen(db, event["id"]):
            return
    checked = time_ns()
    # Fetch the current snapshot rather than trusting the delivery order.
    sub = send("/subscriptions/" + identifier)
    if sub.get("id") != identifier or sub.get("livemode") is not False:
        raise BillingError
    with transaction() as db:
        if _seen(db, event["id"]):
            return
        owner = db.execute(text("""SELECT account_id FROM billing_customers
                      WHERE provider='stripe' AND external_id=:id"""), {"id": sub.get("customer")}).scalar()
        if owner is None:
            return
        items = (sub.get("items") or {}).get("data", [])
        price = None
        if len(items) == 1 and isinstance(items[0], dict):
            item_price = items[0].get("price") or {}
            mapping = db.execute(text("SELECT * FROM commercial_prices WHERE stripe_price=:price"),
                                 {"price": item_price.get("id")}).mappings().first()
            if mapping and items[0].get("quantity") == 1 and _same_price(item_price, mapping):
                price = mapping
        existing = db.execute(text("""SELECT * FROM subscriptions WHERE provider='stripe' AND external_id=:id"""),
                              {"id": identifier}).mappings().first()
        if existing and existing["account_id"] != owner:
            raise InvalidEvent
        status = sub.get("status")
        if status not in (*BLOCK_CHECKOUT, "canceled", "incomplete_expired"):
            raise BillingError
        period = items[0].get("current_period_end", sub.get("current_period_end", 0)) if len(items) == 1 else 0
        if not isinstance(period, int):
            raise BillingError
        if price is None:
            # Unknown price never grants paid access, including after a portal change.
            status, period = "unmapped", 0
            price = existing or dict(plan="monthly", market="", currency="", amount=0)
        apply_subscription(db, SubscriptionSnapshot(
            provider="stripe", external_id=identifier, account_id=owner, plan=price["plan"], status=status,
            period_end=period, cancel_pending=bool(sub.get("cancel_at_period_end") or sub.get("cancel_at")),
            currency=price["currency"], amount=price["amount"], market=price["market"], checked_at=checked,
        ))
        db.execute(text("INSERT INTO billing_events VALUES ('stripe',:event,:owner,:kind,:status,:now)"),
                   dict(event=event["id"], owner=owner, kind=kind, status=status, now=int(time())))
        if kind not in INVOICE_EVENTS:
            db.execute(text("DELETE FROM checkout_pending WHERE account_id=:owner"), {"owner": owner})


def _seen(db, event_id):
    return db.execute(text("SELECT 1 FROM billing_events WHERE provider='stripe' AND event_id=:event"),
                      {"event": event_id}).scalar()
