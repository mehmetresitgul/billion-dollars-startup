import json
from sqlalchemy import String, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from pacifor.models.base import Base, TimestampMixin


class HITLReview(Base, TimestampMixin):
    __tablename__ = "hitl_reviews"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(String, index=True)
    node_name: Mapped[str] = mapped_column(String)
    payload_json: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, default="pending")
    approved: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String, nullable=True)
    decided_at: Mapped[str | None] = mapped_column(String, nullable=True)

    @property
    def payload(self) -> dict:
        return json.loads(self.payload_json)
