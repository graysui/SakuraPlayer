from __future__ import annotations

from datetime import datetime
import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class AdminUser(Base):
    __tablename__ = "admin_user"
    __table_args__ = (
        CheckConstraint("singleton_key", name="ck_admin_user_singleton_key"),
        CheckConstraint(
            "length(username) >= 1",
            name="ck_admin_user_username_not_empty",
        ),
        CheckConstraint(
            "password_hash LIKE '$argon2id$%'",
            name="ck_admin_user_password_argon2id",
        ),
        CheckConstraint("session_epoch >= 0", name="ck_admin_user_session_epoch"),
        UniqueConstraint("singleton_key", name="uq_admin_user_singleton_key"),
        UniqueConstraint("username", name="uq_admin_user_username"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    singleton_key: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    session_epoch: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    refresh_sessions: Mapped[list[RefreshSession]] = relationship(
        back_populates="admin",
        cascade="all, delete-orphan",
    )


class RefreshSession(Base):
    __tablename__ = "refresh_session"
    __table_args__ = (
        CheckConstraint(
            "length(token_hash) = 32",
            name="ck_refresh_session_token_hash_length",
        ),
        UniqueConstraint("token_hash", name="uq_refresh_session_token_hash"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    admin_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("admin_user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[bytes] = mapped_column(
        LargeBinary(32),
        nullable=False,
    )
    client_instance_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    admin: Mapped[AdminUser] = relationship(back_populates="refresh_sessions")


Index(
    "uq_refresh_session_active_client",
    RefreshSession.admin_id,
    RefreshSession.client_instance_id,
    unique=True,
    postgresql_where=RefreshSession.revoked_at.is_(None),
    sqlite_where=RefreshSession.revoked_at.is_(None),
)
