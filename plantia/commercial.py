"""Commercial catalog, account roles, and payment-provider-neutral entitlements."""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from time import time
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from plantia.database import get_engine

FEATURES = ("identify", "diagnosis", "assistant")
PAID = ("plus_monthly", "plus_annual", "monthly", "annual")
ROLES = ("member", "auditor", "admin")
ACTIVE = ("active", "trialing")


class Rules(BaseModel):
    model_config = ConfigDict(extra="forbid")
    free_limit: int = Field(3, ge=0, le=100_000)
    plus_limit: int = Field(50, ge=0, le=100_000)
    free_identify: bool = True
    free_diagnosis: bool = False
    free_assistant: bool = False
    plus_identify: bool = True
    plus_diagnosis: bool = True
    plus_assistant: bool = False
    premium_identify: bool = True
    premium_diagnosis: bool = True
    premium_assistant: bool = True
    plus_credits_enabled: bool = True
    plus_monthly_enabled: bool = True
    plus_annual_enabled: bool = True
    identify: bool = True
    diagnosis: bool = True
    assistant: bool = True
    monthly_enabled: bool = True
    annual_enabled: bool = True
    # Integer micro BRL. Rates are operator-supplied estimates, disabled by default.
    request_micro_brl: int = Field(0, ge=0, le=1_000_000_000)
    input_per_million_micro_brl: int = Field(0, ge=0, le=1_000_000_000)
    output_per_million_micro_brl: int = Field(0, ge=0, le=1_000_000_000)


@contextmanager
def transaction():
    with get_engine().begin() as db:
        db.exec_driver_sql("BEGIN IMMEDIATE")
        yield db


def init():
    with transaction() as db:
        columns = {row[1] for row in db.exec_driver_sql("PRAGMA table_info(accounts)")}
        if "commercial_role" not in columns:
            db.exec_driver_sql("ALTER TABLE accounts ADD COLUMN commercial_role TEXT NOT NULL DEFAULT 'member'")
        if "suspended" not in columns:
            db.exec_driver_sql("ALTER TABLE accounts ADD COLUMN suspended INTEGER NOT NULL DEFAULT 0")
        for statement in (
            """CREATE TABLE IF NOT EXISTS commercial_installation (id INTEGER PRIMARY KEY CHECK(id=1), namespace TEXT NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS commercial_rules (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS commercial_prices (
                id INTEGER PRIMARY KEY, market TEXT NOT NULL, plan TEXT NOT NULL, currency TEXT NOT NULL,
                amount INTEGER NOT NULL, stripe_price TEXT UNIQUE, enabled INTEGER NOT NULL)""",
            """CREATE UNIQUE INDEX IF NOT EXISTS commercial_price_active ON commercial_prices(market,plan) WHERE enabled=1""",
            """CREATE TABLE IF NOT EXISTS billing_customers (
                account_id INTEGER PRIMARY KEY REFERENCES accounts(id), provider TEXT NOT NULL,
                external_id TEXT NOT NULL, UNIQUE(provider,external_id))""",
            """CREATE TABLE IF NOT EXISTS subscriptions (
                provider TEXT NOT NULL, external_id TEXT NOT NULL, account_id INTEGER NOT NULL REFERENCES accounts(id),
                plan TEXT NOT NULL, status TEXT NOT NULL, period_end INTEGER NOT NULL, cancel_pending INTEGER NOT NULL,
                currency TEXT NOT NULL, amount INTEGER NOT NULL, market TEXT NOT NULL, checked_at INTEGER NOT NULL,
                PRIMARY KEY(provider,external_id))""",
            """CREATE INDEX IF NOT EXISTS subscriptions_account ON subscriptions(account_id,period_end)""",
            """CREATE TABLE IF NOT EXISTS billing_events (
                provider TEXT NOT NULL, event_id TEXT NOT NULL, account_id INTEGER, kind TEXT NOT NULL,
                status TEXT NOT NULL, received_at INTEGER NOT NULL, PRIMARY KEY(provider,event_id))""",
            """CREATE TABLE IF NOT EXISTS checkout_pending (
                account_id INTEGER PRIMARY KEY REFERENCES accounts(id), price_id INTEGER NOT NULL,
                request_key TEXT NOT NULL, expires INTEGER NOT NULL, url TEXT)""",
            """CREATE TABLE IF NOT EXISTS site_media (
                key TEXT PRIMARY KEY, url TEXT NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS commercial_audit (
                id INTEGER PRIMARY KEY, actor INTEGER NOT NULL, action TEXT NOT NULL,
                target TEXT NOT NULL, details TEXT NOT NULL, created_at INTEGER NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS ai_meter (
                id INTEGER PRIMARY KEY, account_id INTEGER NOT NULL REFERENCES accounts(id), feature TEXT NOT NULL,
                created_at INTEGER NOT NULL, state TEXT NOT NULL, input_tokens INTEGER NOT NULL DEFAULT 0,
                output_tokens INTEGER NOT NULL DEFAULT 0, token_reported INTEGER NOT NULL DEFAULT 0,
                estimated_cost INTEGER NOT NULL DEFAULT 0, error_code TEXT)""",
            """CREATE INDEX IF NOT EXISTS ai_meter_account_month ON ai_meter(account_id,created_at)""",
        ):
            db.exec_driver_sql(statement)
        db.execute(text("INSERT OR IGNORE INTO commercial_installation VALUES (1,:ns)"), {"ns": uuid4().hex})
        db.execute(text("INSERT OR IGNORE INTO commercial_rules VALUES (1,:payload)"), {"payload": Rules().model_dump_json()})
        db.exec_driver_sql("""CREATE TABLE IF NOT EXISTS plus_credit_ledger (
            id INTEGER PRIMARY KEY, account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
            amount INTEGER NOT NULL, created_at INTEGER NOT NULL)""")
        db.exec_driver_sql("CREATE INDEX IF NOT EXISTS plus_credit_account ON plus_credit_ledger(account_id)")
        meter_columns = {row[1] for row in db.exec_driver_sql("PRAGMA table_info(ai_meter)")}
        if "provider_calls" not in meter_columns:
            db.exec_driver_sql("ALTER TABLE ai_meter ADD COLUMN provider_calls INTEGER")
            db.exec_driver_sql("ALTER TABLE ai_meter ADD COLUMN model TEXT")
        payload = json.loads(db.exec_driver_sql("SELECT payload FROM commercial_rules WHERE id=1").scalar_one())
        if "monthly_limit" in payload or "annual_limit" in payload:
            payload.pop("monthly_limit", None)
            payload.pop("annual_limit", None)
            payload["free_limit"] = 3
            db.execute(text("UPDATE commercial_rules SET payload=:rules WHERE id=1"),
                       {"rules": Rules.model_validate(payload).model_dump_json()})
        for plan, amount in {"plus_monthly": 1990, "plus_annual": 14990,
                             "monthly": 2990, "annual": 19990}.items():
            db.execute(text("""INSERT INTO commercial_prices(market,plan,currency,amount,stripe_price,enabled)
              SELECT 'BR',:plan,'BRL',:amount,NULL,1
              WHERE NOT EXISTS (SELECT 1 FROM commercial_prices WHERE market='BR' AND plan=:plan)"""),
                       {"plan": plan, "amount": amount})
        from plantia.services.stripe_billing import bind_database
        bind_database(db)


def rules(db):
    return Rules.model_validate_json(db.execute(text("SELECT payload FROM commercial_rules WHERE id=1")).scalar_one())


def current_subscription(db, owner):
    return db.execute(text("""SELECT * FROM subscriptions WHERE account_id=:owner
        ORDER BY (status IN ('active','trialing') AND period_end>:now) DESC,
                 checked_at DESC, period_end DESC LIMIT 1"""), {"owner": owner, "now": int(time())}).mappings().first()


def entitled(subscription):
    return bool(subscription and subscription["status"] in ACTIVE and subscription["period_end"] > int(time()))


def introduction_video(db):
    return db.execute(text("SELECT url FROM site_media WHERE key='introduction'")).scalar()


def set_introduction_video(db, actor, url):
    if url:
        db.execute(text("""INSERT INTO site_media VALUES ('introduction', :url)
            ON CONFLICT(key) DO UPDATE SET url=excluded.url"""), {"url": url})
    else:
        db.execute(text("DELETE FROM site_media WHERE key='introduction'"))
    audit(db, actor, "video.edit", "introduction", {"enabled": bool(url)})


def month_start():
    return int(datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp())


def tier(plan):
    if plan in {"monthly", "annual"}:
        return "premium"
    if plan in {"plus_monthly", "plus_annual"}:
        return "plus"
    return "free"


def active_plan(db, owner):
    sub = current_subscription(db, owner)
    return sub["plan"] if entitled(sub) else "free"


def benefits(config, level):
    return {feature: getattr(config, feature) and getattr(config, f"{level}_{feature}")
            for feature in FEATURES}


def credit_balance(db, owner):
    return db.execute(text("SELECT coalesce(sum(amount),0) FROM plus_credit_ledger WHERE account_id=:owner"),
                      {"owner": owner}).scalar_one()


def add_credits(db, owner, amount):
    db.execute(text("INSERT INTO plus_credit_ledger(account_id,amount,created_at) VALUES (:owner,:amount,:now)"),
               {"owner": owner, "amount": amount, "now": int(time())})


def allowance(db, owner):
    config = rules(db)
    plan = active_plan(db, owner)
    level = tier(plan)
    limit = None if level == "premium" else getattr(config, level + "_limit")
    used = db.execute(text("SELECT count(*) FROM ai_meter WHERE account_id=:owner AND created_at>=:start"),
                      {"owner": owner, "start": month_start()}).scalar_one()
    credits = credit_balance(db, owner) if level == "plus" and config.plus_credits_enabled else 0
    return {"plan": plan, "tier": level, "limit": limit, "used": used, "credits": credits,
            "remaining": None if limit is None else max(0, limit - used) + credits,
            "benefits": benefits(config, level)}


def audit(db, actor, action, target, details):
    db.execute(text("""INSERT INTO commercial_audit(actor,action,target,details,created_at)
        VALUES (:actor,:action,:target,:details,:created)"""),
        {"actor": actor, "action": action, "target": str(target),
         "details": json.dumps(details, ensure_ascii=False, sort_keys=True), "created": int(time())})


def role(db, owner):
    return db.execute(text("SELECT commercial_role FROM accounts WHERE id=:owner AND suspended=0"),
                      {"owner": owner}).scalar() if owner else None


def public_price(row):
    return {key: row[key] for key in ("id", "market", "plan", "currency", "amount")}


def put_price(db, actor, market, plan, currency, amount, price_id, enabled=True):
    same = db.execute(text("SELECT * FROM commercial_prices WHERE stripe_price=:price"),
                      {"price": price_id}).mappings().first() if price_id else None
    if same and any(same[k] != v for k, v in dict(market=market, plan=plan, currency=currency, amount=amount).items()):
        raise ValueError("immutable Stripe mapping")
    if enabled:
        db.execute(text("UPDATE commercial_prices SET enabled=0 WHERE market=:market AND plan=:plan"),
                   {"market": market, "plan": plan})
        if same:
            db.execute(text("UPDATE commercial_prices SET enabled=1 WHERE id=:id"), {"id": same["id"]})
        else:
            db.execute(text("""INSERT INTO commercial_prices(market,plan,currency,amount,stripe_price,enabled)
                VALUES (:market,:plan,:currency,:amount,:price,1)"""),
                {"market": market, "plan": plan, "currency": currency, "amount": amount, "price": price_id})
    else:
        db.execute(text("UPDATE commercial_prices SET enabled=0 WHERE market=:market AND plan=:plan"),
                   {"market": market, "plan": plan})
    audit(db, actor, "price.edit", f"{market}:{plan}", {"currency": currency, "amount": amount, "enabled": enabled})


class SubscriptionSnapshot(BaseModel):
    """Input from a server-verified payment provider, never directly from a client."""

    provider: str
    external_id: str
    account_id: int
    plan: str
    status: str
    period_end: int
    cancel_pending: bool
    currency: str
    amount: int
    market: str
    checked_at: int


def apply_subscription(db, subscription: SubscriptionSnapshot):
    result = db.execute(text("""INSERT INTO subscriptions VALUES
        (:provider,:external_id,:account_id,:plan,:status,:period_end,:cancel_pending,:currency,:amount,:market,:checked_at)
        ON CONFLICT(provider,external_id) DO UPDATE SET plan=excluded.plan,status=excluded.status,
          period_end=excluded.period_end,cancel_pending=excluded.cancel_pending,currency=excluded.currency,
          amount=excluded.amount,market=excluded.market,checked_at=excluded.checked_at
        WHERE excluded.account_id = subscriptions.account_id AND excluded.checked_at >= subscriptions.checked_at"""),
        subscription.model_dump())
    return bool(result.rowcount)
