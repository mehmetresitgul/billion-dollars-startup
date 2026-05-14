from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column
from pacifor.models.base import Base, TimestampMixin


class KillEvent(Base, TimestampMixin):
    __tablename__ = "kill_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    action: Mapped[str] = mapped_column(String)  # "engage" | "release"
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
    triggered_by: Mapped[str | None] = mapped_column(String, nullable=True)
