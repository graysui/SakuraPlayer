from __future__ import annotations

from datetime import datetime
import uuid

from sqlalchemy import CheckConstraint, DateTime, Index, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from sakuraplayer.identity.models import Base


class Favorite(Base):
    __tablename__ = "favorite"
    __table_args__ = (
        CheckConstraint(
            "target_type IN ('movie', 'actor')",
            name="ck_favorite_target_type",
        ),
        UniqueConstraint(
            "target_type",
            "target_id",
            name="uq_favorite_target",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    target_type: Mapped[str] = mapped_column(String(16), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )


Index(
    "ix_favorite_target_created",
    Favorite.target_type,
    Favorite.created_at,
    Favorite.target_id,
)


__all__ = ["Favorite"]
