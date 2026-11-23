"""Account subscriptions, signed Stripe events and operator controls."""

from datetime import datetime, timezone
import re
from typing import Literal

from fastapi import APIRouter, Form, HTTPException, Query, Request
from pydantic import ValidationError
from sqlalchemy import text
from starlette.concurrency import run_in_threadpool
from starlette.responses import RedirectResponse

from plantia import commercial as billing
from plantia.database import get_engine
from plantia.i18n import catalog, locale_for
from plantia.services import stripe_billing as stripe

router = APIRouter()
CURRENCIES = ("BRL", "USD", "EUR", "GBP", "JPY", "CAD", "AUD", "MXN", "INR", "SAR", "KRW", "CNY", "CHF")


def _render(request, template, data):
    if request.url.path.startswith("/api/"):
        return data
    from plantia.api.routes import templates
    return templates.TemplateResponse(request, template, data)


def _timestamp(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat() if value else None


@router.get("/assinatura")
@router.get("/api/assinatura")
def subscription(request: Request, market: str = Query("BR", pattern=r"^[A-Z]{2}$")):
    owner = request.state.account_id
    with get_engine().connect() as db:
        config = billing.rules(db)
        sub = billing.current_subscription(db, owner)
        prices = db.execute(text("""SELECT * FROM commercial_prices
            WHERE market=:market AND enabled=1 ORDER BY amount"""), {"market": market}).mappings().all()
        markets = db.execute(text("SELECT DISTINCT market FROM commercial_prices WHERE enabled=1 ORDER BY market")).scalars().all()
        history = db.execute(text("""SELECT kind,status,received_at FROM billing_events
            WHERE account_id=:owner ORDER BY received_at DESC LIMIT 20"""), {"owner": owner}).mappings().all()
        ready = stripe.ready()
        data = {"usage": billing.allowance(db, owner), "market": market, "markets": markets,
                "prices": [{**billing.public_price(p), "limit": getattr(config, p["plan"] + "_limit"),
                            "checkout": bool(ready and p["stripe_price"] and not (
                                sub and sub["status"] in stripe.BLOCK_CHECKOUT))}
                           for p in prices if getattr(config, p["plan"] + "_enabled")],
                "free_limit": config.free_limit, "test_mode": True,
                "portal": ready and bool(stripe.account_customer(owner)),
                "operator": billing.role(db, owner) in {"admin", "auditor"},
                "subscription": {**{k: sub[k] for k in ("plan", "provider")},
                                 "status": "expired" if sub["status"] in billing.ACTIVE and not billing.entitled(sub) else sub["status"],
                                 "cancel_pending": bool(sub["cancel_pending"]),
                                 "period_end": _timestamp(sub["period_end"])} if sub else None,
                "history": [{**row, "date": _timestamp(row["received_at"])} for row in history]}
    if request.url.path.startswith("/api/"):
        messages = catalog(locale_for(request))
        data["labels"] = {key: value for key, value in messages.items() if key.startswith("commercial.") and (
            key.startswith(("commercial.plan.", "commercial.status.")) or key in {
                "commercial.title", "commercial.remaining", "commercial.cancel_pending"
            })}
    return _render(request, "subscription.html", data)


def _payment(function, *args):
    try:
        return RedirectResponse(function(*args), 303)
    except stripe.BillingConflict:
        raise HTTPException(409, "commercial.pending") from None
    except stripe.BillingError:
        _operational("stripe_unavailable")
        raise HTTPException(503, "commercial.payment_unavailable") from None


@router.post("/assinatura/checkout")
def checkout(request: Request, price: int = Form(...)):
    return _payment(stripe.checkout, request.state.account_id, price)


@router.post("/assinatura/portal")
def portal(request: Request):
    return _payment(stripe.portal, request.state.account_id)


@router.post("/api/stripe/webhook")
async def webhook(request: Request):
    payload = bytearray()
    async for chunk in request.stream():
        if len(payload) + len(chunk) > 256 * 1024:
            raise HTTPException(413, "File or request too large")
        payload.extend(chunk)
    try:
        event = stripe.verify(bytes(payload), request.headers.get("stripe-signature", ""))
        await run_in_threadpool(stripe.webhook, event)
    except stripe.InvalidEvent:
        raise HTTPException(400, "Invalid request") from None
    except stripe.BillingError:
        await run_in_threadpool(_operational, "stripe_webhook_retry")
        raise HTTPException(503, "commercial.payment_unavailable") from None
    return {"received": True}


def _operational(code):
    with billing.transaction() as db:
        billing.audit(db, 0, "error", "stripe", {"code": code})


def _require(db, request, write=False):
    actor = request.state.account_id
    role = billing.role(db, actor)
    if role not in (("admin",) if write else ("admin", "auditor")):
        raise HTTPException(403, "Request blocked")
    return actor, role


@router.get("/admin/comercial")
def dashboard(request: Request, page: int = Query(1, ge=1, le=100_000)):
    from time import time

    with get_engine().connect() as db:
        _, role = _require(db, request)
        now, start = int(time()), billing.month_start()
        params = {"now": now, "start": start, "offset": (page - 1) * 40}
        stats = dict(db.execute(text("""SELECT count(*) registered,
            coalesce(sum(suspended),0) suspended,
            count(*) FILTER (WHERE suspended=0 AND EXISTS
            (SELECT 1 FROM account_tokens t WHERE t.account_id=accounts.id AND t.purpose='session' AND t.expires>:now)) active
            FROM accounts"""), params).mappings().one())
        stats["premium"] = db.execute(text("""SELECT count(DISTINCT account_id) FROM subscriptions
             WHERE status IN ('active','trialing') AND period_end>:now"""), params).scalar_one()
        stats["free"] = stats["registered"] - stats["premium"]
        stats["canceled"] = db.execute(text("""SELECT count(DISTINCT s.account_id) FROM subscriptions s
            WHERE (s.status='canceled' OR s.cancel_pending=1) AND NOT EXISTS
            (SELECT 1 FROM subscriptions newer WHERE newer.account_id=s.account_id AND newer.checked_at>s.checked_at)""")).scalar_one()
        revenue = db.execute(text("""SELECT currency,sum(CASE WHEN plan='annual' THEN amount/12.0 ELSE amount END) minor
            FROM subscriptions WHERE status='active' AND period_end>:now GROUP BY currency"""), params).mappings().all()
        usage = db.execute(text("""SELECT feature,count(*) requests,sum(input_tokens) input_tokens,sum(output_tokens) output_tokens,
            sum(token_reported) reports,sum(estimated_cost) cost,count(*) FILTER(WHERE state='failed') errors
            FROM ai_meter WHERE created_at>=:start GROUP BY feature ORDER BY requests DESC"""), params).mappings().all()
        costs = sum(row["cost"] for row in usage)
        brl = next((row["minor"] / 100 for row in revenue if row["currency"] == "BRL"), 0)
        buying_other_currency = any(row["currency"] != "BRL" for row in revenue)
        users = db.execute(text("""SELECT id,email,commercial_role,suspended FROM accounts
            ORDER BY id DESC LIMIT 41 OFFSET :offset"""), params).mappings().all()
        history = db.execute(text("""SELECT account_id,kind,status,received_at FROM billing_events
            ORDER BY received_at DESC LIMIT 30""")).mappings().all()
        audit = db.execute(text("""SELECT actor,action,target,details,created_at FROM commercial_audit
            ORDER BY id DESC LIMIT 40""")).mappings().all()
        prices = db.execute(text("""SELECT market,plan,currency,amount,stripe_price,enabled
            FROM commercial_prices WHERE enabled=1 ORDER BY market,plan""")).mappings().all()
        config = billing.rules(db).model_dump()
    return _render(request, "commercial_admin.html", {
        "editable": role == "admin", "stats": stats, "revenue": revenue, "usage": usage, "cost_brl": costs / 1e6,
        "margin_brl": None if buying_other_currency else brl - costs / 1e6,
        "margin_percent": (brl - costs / 1e6) / brl if brl > 0 and not buying_other_currency else None,
        "users": users[:40], "history": history, "audit": audit, "prices": prices, "config": config,
        "currencies": CURRENCIES, "page": page, "more": len(users) > 40, "timestamp": _timestamp,
    })


@router.post("/admin/comercial/configuracao")
async def edit_rules(request: Request):
    form = await request.form()
    knobs = billing.Rules.model_fields
    try:
        candidate = billing.Rules.model_validate({
            key: form.get(key, "false") if field.annotation is bool else form.get(key)
            for key, field in knobs.items()
        })
    except ValidationError:
        raise HTTPException(400, "Invalid request") from None

    def save():
        with billing.transaction() as db:
            actor, _ = _require(db, request, write=True)
            db.execute(text("UPDATE commercial_rules SET payload=:payload WHERE id=1"), {"payload": candidate.model_dump_json()})
            billing.audit(db, actor, "rules.edit", "rules", candidate.model_dump())

    await run_in_threadpool(save)
    return RedirectResponse("/admin/comercial", 303)


@router.post("/admin/comercial/preco")
def edit_price(request: Request, market: str = Form(..., pattern=r"^[A-Z]{2}$"),
               plan: Literal["monthly", "annual"] = Form(...), currency: str = Form(...),
               amount: int = Form(..., ge=1, le=99_999_999), stripe_price: str = Form("", max_length=100),
               enabled: bool = Form(False)):
    if currency not in CURRENCIES or (stripe_price and not re.fullmatch(r"price_[A-Za-z0-9]+", stripe_price)):
        raise HTTPException(400, "Invalid request")
    with billing.transaction() as db:
        actor, _ = _require(db, request, write=True)
        try:
            billing.put_price(db, actor, market, plan, currency, amount, stripe_price or None, enabled)
        except ValueError:
            raise HTTPException(409, "commercial.immutable_price") from None
    return RedirectResponse("/admin/comercial", 303)


@router.post("/admin/comercial/contas/{owner}")
def edit_account(request: Request, owner: int, role: Literal["member", "auditor", "admin"] = Form(...),
                 suspended: bool = Form(False)):
    with billing.transaction() as db:
        actor, _ = _require(db, request, write=True)
        if actor == owner and (role != "admin" or suspended):
            raise HTTPException(409, "commercial.self_role")
        result = db.execute(text("""UPDATE accounts SET commercial_role=:role,suspended=:suspended WHERE id=:owner"""),
                            {"role": role, "suspended": int(suspended), "owner": owner})
        if not result.rowcount:
            raise HTTPException(404, "Not found")
        if suspended:
            db.execute(text("DELETE FROM account_tokens WHERE account_id=:owner"), {"owner": owner})
        billing.audit(db, actor, "account.edit", owner, {"role": role, "suspended": suspended})
    return RedirectResponse("/admin/comercial", 303)
