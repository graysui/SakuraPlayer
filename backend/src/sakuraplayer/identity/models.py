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
    JSON,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


_JSON_VALUE = JSON(none_as_null=True).with_variant(
    JSONB(none_as_null=True),
    "postgresql",
)


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


class EncryptedSetting(Base):
    __tablename__ = "encrypted_setting"
    __table_args__ = (
        CheckConstraint(
            "length(key) >= 1",
            name="ck_encrypted_setting_key_not_empty",
        ),
        CheckConstraint(
            "(public_value IS NOT NULL AND key_id IS NULL "
            "AND nonce IS NULL AND ciphertext IS NULL) OR "
            "(public_value IS NULL AND key_id IS NOT NULL "
            "AND nonce IS NOT NULL AND ciphertext IS NOT NULL)",
            name="ck_encrypted_setting_value_shape",
        ),
        CheckConstraint(
            "key_id IS NULL OR length(key_id) >= 1",
            name="ck_encrypted_setting_key_id_not_empty",
        ),
        CheckConstraint(
            "nonce IS NULL OR length(nonce) = 12",
            name="ck_encrypted_setting_nonce_length",
        ),
        CheckConstraint(
            "ciphertext IS NULL OR length(ciphertext) >= 16",
            name="ck_encrypted_setting_ciphertext_length",
        ),
        CheckConstraint("version >= 1", name="ck_encrypted_setting_version"),
    )

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    public_value: Mapped[object | None] = mapped_column(
        _JSON_VALUE,
        nullable=True,
    )
    key_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    nonce: Mapped[bytes | None] = mapped_column(LargeBinary(12), nullable=True)
    ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )


class ConnectionTestResult(Base):
    __tablename__ = "connection_test_result"
    __table_args__ = (
        CheckConstraint(
            "target IN ('cloud115', 'javdb', 'dmm', 'gfriends', 'ai')",
            name="ck_connection_test_target",
        ),
        CheckConstraint(
            "status IN ('available', 'unavailable', 'credentials_invalid', "
            "'not_configured')",
            name="ck_connection_test_status",
        ),
        CheckConstraint("elapsed_ms >= 0", name="ck_connection_test_elapsed"),
    )

    target: Mapped[str] = mapped_column(String(16), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(128))
    elapsed_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
