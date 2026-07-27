from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from sakuraplayer.identity.models import Base


class Cloud115Binding(Base):
    __tablename__ = "cloud115_binding"
    __table_args__ = (
        CheckConstraint(
            "singleton_key",
            name="ck_cloud115_binding_singleton_key",
        ),
        CheckConstraint(
            "length(account_key) BETWEEN 1 AND 128",
            name="ck_cloud115_binding_account_key",
        ),
        CheckConstraint(
            "cookie_setting_key = 'cloud115.cookie'",
            name="ck_cloud115_binding_cookie_key",
        ),
        CheckConstraint(
            "login_app = 'alipaymini'",
            name="ck_cloud115_binding_login_app",
        ),
        CheckConstraint(
            "length(cache_root_cid) BETWEEN 1 AND 64",
            name="ck_cloud115_binding_root_cid",
        ),
        CheckConstraint(
            "status IN ('active', 'expired', 'unavailable', 'detached')",
            name="ck_cloud115_binding_status",
        ),
        CheckConstraint(
            "credential_version >= 1",
            name="ck_cloud115_binding_credential_version",
        ),
        UniqueConstraint(
            "singleton_key",
            name="uq_cloud115_binding_singleton_key",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    singleton_key: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    account_key: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(128))
    cookie_setting_key: Mapped[str] = mapped_column(
        ForeignKey("encrypted_setting.key", ondelete="RESTRICT"),
        nullable=False,
        default="cloud115.cookie",
    )
    login_app: Mapped[str] = mapped_column(
        String(32), nullable=False, default="alipaymini"
    )
    cache_root_cid: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    credential_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


__all__ = ["Cloud115Binding"]
