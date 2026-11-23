"""Atomic monthly quotas and Gemini usage accounting."""

from contextlib import contextmanager
from contextvars import ContextVar
from time import time

from fastapi import HTTPException
from sqlalchemy import text

from plantia.commercial import allowance, rules, transaction
from plantia.database import get_engine

_active = ContextVar("planet_ai_usage", default=None)


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
        if not getattr(config, feature):
            raise HTTPException(403, "commercial.disabled")
        if not allowance(db, owner)["remaining"]:
            raise HTTPException(429, "commercial.quota")
        record = db.execute(text("""INSERT INTO ai_meter(account_id,feature,created_at,state)
            VALUES (:owner,:feature,:now,'running')"""),
            {"owner": owner, "feature": feature, "now": int(time())}).lastrowid
    entry = [0, 0, False]
    token = _active.set(entry)
    state, error = "success", None
    try:
        yield
    except Exception:
        state, error = "failed", "provider_or_processing_failure"
        raise
    finally:
        _active.reset(token)
        cost = config.request_micro_brl + (
            entry[0] * config.input_per_million_micro_brl + entry[1] * config.output_per_million_micro_brl
        ) // 1_000_000
        with get_engine().begin() as db:
            db.execute(text("""UPDATE ai_meter SET state=:state,input_tokens=:inp,
                output_tokens=:out,token_reported=:reported,estimated_cost=:cost,error_code=:error WHERE id=:record"""),
                       dict(state=state, inp=entry[0], out=entry[1], reported=int(entry[2]), cost=cost,
                            error=error, record=record))
