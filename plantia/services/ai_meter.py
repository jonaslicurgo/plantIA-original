"""Atomic monthly quotas and Gemini usage accounting."""

from contextlib import contextmanager
from contextvars import ContextVar
from time import time

from fastapi import HTTPException
from sqlalchemy import text

from plantia.commercial import active_plan, add_credits, allowance, benefits, rules, tier, transaction
from plantia.database import get_engine

_active = ContextVar("planet_ai_usage", default=None)


def _authorize(db, owner, feature, config):
    if not benefits(config, tier(active_plan(db, owner)))[feature]:
        raise HTTPException(403, "commercial.disabled")


def check_access(owner, feature):
    with get_engine().connect() as db:
        _authorize(db, owner, feature, rules(db))


def available_features(owner):
    with get_engine().connect() as db:
        return benefits(rules(db), tier(active_plan(db, owner)))


def provider_attempt(model):
    entry = _active.get()
    if entry is not None:
        entry[3] += 1
        entry[4] = model
        with get_engine().begin() as db:
            db.execute(text("UPDATE ai_meter SET provider_calls=:calls, model=:model WHERE id=:record"),
                       {"calls": entry[3], "model": model, "record": entry[5]})


def capture(response):
    entry = _active.get()
    metadata = getattr(response, "usage_metadata", None)
    if entry is None or metadata is None:
        return
    get = lambda key: getattr(metadata, key, None)
    values = [get("prompt_token_count"), get("candidates_token_count"), get("thoughts_token_count")]
    if any(isinstance(v, int) and v >= 0 for v in values):
        entry[2] = True
        for idx, value in enumerate(values):
            if isinstance(value, int) and value >= 0:
                entry[min(idx, 1)] += value


@contextmanager
def measure(owner, feature):
    with transaction() as db:
        config = rules(db)
        _authorize(db, owner, feature, config)
        usage = allowance(db, owner)
        if usage["limit"] is None:
            running = db.execute(text("""SELECT 1 FROM ai_meter WHERE account_id=:owner
                AND state='running' AND created_at>:since LIMIT 1"""),
                {"owner": owner, "since": int(time()) - 120}).first()
            if running:
                raise HTTPException(429, "commercial.concurrent")
        elif not usage["remaining"]:
            raise HTTPException(429, "commercial.quota")
        elif usage["used"] >= usage["limit"]:
            add_credits(db, owner, -1)
        record = db.execute(text("""INSERT INTO ai_meter(account_id,feature,created_at,state)
            VALUES (:owner,:feature,:now,'running')"""),
            {"owner": owner, "feature": feature, "now": int(time())}).lastrowid
    entry = [0, 0, False, 0, None, record]
    token = _active.set(entry)
    state, error = "success", None
    try:
        yield
    except Exception:
        state, error = "failed", "provider_or_processing_failure"
        raise
    finally:
        _active.reset(token)
        cost = config.request_micro_brl * entry[3] + (
            entry[0] * config.input_per_million_micro_brl + entry[1] * config.output_per_million_micro_brl
        ) // 1_000_000
        with get_engine().begin() as db:
            db.execute(text("""UPDATE ai_meter SET state=:state,input_tokens=:inp,
                output_tokens=:out,token_reported=:reported,estimated_cost=:cost,error_code=:error,provider_calls=:calls,model=:model WHERE id=:record"""),
                       dict(state=state, inp=entry[0], out=entry[1], reported=int(entry[2]), cost=cost,
                            error=error, calls=entry[3], model=entry[4], record=record))
