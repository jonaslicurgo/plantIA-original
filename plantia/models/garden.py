from datetime import date, datetime

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from plantia.models.base import Base


class GardenProfile(Base):
    __tablename__ = "garden_profiles"

    plant_id: Mapped[int] = mapped_column(ForeignKey("plantas.id", ondelete="CASCADE"), primary_key=True)
    nickname: Mapped[str] = mapped_column(String(80))
    location: Mapped[str] = mapped_column(String(80))


class GardenTask(Base):
    __tablename__ = "garden_tasks"
    __table_args__ = (Index("ix_garden_tasks_plant_due", "plant_id", "due_on"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    plant_id: Mapped[int] = mapped_column(ForeignKey("plantas.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(16))
    due_on: Mapped[date]
    completed_at: Mapped[datetime | None]
