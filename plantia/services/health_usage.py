"""Persistent provider usage and duplicate suppression for health operations."""

import hashlib
import json
from time import time

from sqlalchemy import func, select

from plantia.database import session_scope
from plantia.models import HealthAIUsage, HealthEvent, Planta
from plantia.services.health import serialize


DEFAULT_HOURLY_LIMIT = 10


def hourly_limit(owner):
    """Policy boundary for future subscription or credit-based allowances."""
    return DEFAULT_HOURLY_LIMIT


class Busy(Exception):
    pass


class Limit(Exception):
    pass


def fingerprint(operation, model, context, photo=b""):
    data = json.dumps(["health-v2", operation, model, context], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(data.encode() + b"\0" + photo).hexdigest()


def reserve(owner, plant, operation, key):
    now = int(time())
    with session_scope() as db:
        db.connection().exec_driver_sql("BEGIN IMMEDIATE")
        if db.scalar(select(Planta.id).where(Planta.id == plant, Planta.owner_id == owner)) is None:
            return None, None
        match = db.scalar(select(HealthAIUsage).where(
            HealthAIUsage.owner_id == owner, HealthAIUsage.plant_id == plant,
            HealthAIUsage.fingerprint == key, HealthAIUsage.state.in_(("running", "success")),
            HealthAIUsage.created_at > now - 86400,
        ).order_by(HealthAIUsage.id.desc()).limit(1))
        if match and match.state == "running" and match.created_at > now - 120:
            raise Busy
        if match and match.state == "success" and match.event_id:
            event = db.get(HealthEvent, match.event_id)
            if event is not None and event.plant_id == plant:
                return None, serialize(event)
        count = db.scalar(select(func.count()).select_from(HealthAIUsage).where(
            HealthAIUsage.owner_id == owner, HealthAIUsage.created_at > now - 3600,
            HealthAIUsage.state != "rejected",
        ))
        if count >= hourly_limit(owner):
            raise Limit
        usage = HealthAIUsage(owner_id=owner, plant_id=plant, operation=operation,
                              fingerprint=key, created_at=now, state="running")
        db.add(usage)
        db.flush()
        return usage.id, None


def finish(usage_id, state, event_id=None):
    with session_scope() as db:
        usage = db.get(HealthAIUsage, usage_id)
        if usage:
            usage.state = state
            if event_id and db.get(HealthEvent, event_id):
                usage.event_id = event_id


def totals(owner):
    with session_scope() as db:
        rows = db.execute(select(HealthAIUsage.operation, HealthAIUsage.state, func.count()).where(
            HealthAIUsage.owner_id == owner, HealthAIUsage.created_at > int(time()) - 3600
        ).group_by(HealthAIUsage.operation, HealthAIUsage.state))
        result = {"attempts": 0, "successful": 0, "assessments": 0, "assistant": 0, "hourly_limit": hourly_limit(owner)}
        for operation, state, count in rows:
            if state != "rejected":
                result["attempts"] += count
                result["assessments" if operation == "assess" else "assistant"] += count
            if state == "success":
                result["successful"] += count
        return result
