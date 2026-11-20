"""Private, per-specimen plant health history."""

from sqlalchemy import ForeignKey, Index, LargeBinary, Text
from sqlalchemy.orm import Mapped, mapped_column

from plantia.models.base import Base


class HealthEvent(Base):
    __tablename__ = "plant_health_events"
    __table_args__ = (Index("ix_health_plant_date", "plant_id", "id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    plant_id: Mapped[int] = mapped_column(ForeignKey("plantas.id", ondelete="CASCADE"))
    created_at: Mapped[int]
    kind: Mapped[str]
    payload: Mapped[str] = mapped_column(Text)
    photo: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)


class HealthAIUsage(Base):
    __tablename__ = "health_ai_usage"
    __table_args__ = (
        Index("ix_health_ai_owner_time", "owner_id", "created_at"),
        Index("ix_health_ai_cache", "owner_id", "plant_id", "fingerprint", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int]
    plant_id: Mapped[int]
    event_id: Mapped[int | None] = mapped_column(ForeignKey("plant_health_events.id", ondelete="SET NULL"))
    created_at: Mapped[int]
    operation: Mapped[str]
    fingerprint: Mapped[str]
    state: Mapped[str]
