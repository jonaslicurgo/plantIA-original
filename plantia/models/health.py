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
