from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from sakuraplayer.identity.crypto import EncryptedEnvelope, SecretCipher
from sakuraplayer.identity.models import EncryptedSetting


class SettingAlreadyExists(RuntimeError):
    code = "setting_already_exists"

    def __init__(self) -> None:
        super().__init__(self.code)


class ConcurrentSettingUpdate(RuntimeError):
    code = "setting_version_conflict"

    def __init__(self) -> None:
        super().__init__(self.code)


@dataclass(frozen=True)
class SecretSetting:
    key: str
    value: bytes = field(repr=False)
    version: int
    updated_at: datetime


@dataclass(frozen=True)
class SettingStatus:
    key: str
    configured: bool
    version: int
    updated_at: datetime


@dataclass(frozen=True)
class PublicSetting:
    key: str
    value: object
    version: int
    updated_at: datetime


_CLEARED_SECRET = {"sakuraplayer_secret_state": "cleared"}


class EncryptedSettingRepository:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        cipher: SecretCipher,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._cipher = cipher
        self._now = now or (lambda: datetime.now(timezone.utc))

    def create_secret(self, key: str, value: bytes) -> SecretSetting:
        context = self._context(key)
        envelope = self._cipher.encrypt(value, context=context)
        updated_at = self._now()
        try:
            with self._session_factory.begin() as session:
                session.execute(
                    insert(EncryptedSetting).values(
                        key=key,
                        public_value=None,
                        key_id=envelope.key_id,
                        nonce=envelope.nonce,
                        ciphertext=envelope.ciphertext,
                        version=1,
                        updated_at=updated_at,
                    )
                )
        except IntegrityError:
            raise SettingAlreadyExists from None
        return SecretSetting(
            key=key,
            value=value,
            version=1,
            updated_at=updated_at,
        )

    def create_or_compare_and_set_secret(
        self,
        key: str,
        *,
        expected_version: int,
        value: bytes,
    ) -> SecretSetting:
        if expected_version == 0:
            try:
                return self.create_secret(key, value)
            except SettingAlreadyExists:
                raise ConcurrentSettingUpdate from None
        return self.compare_and_set_secret(
            key,
            expected_version=expected_version,
            value=value,
        )

    def compare_and_set_secret(
        self,
        key: str,
        *,
        expected_version: int,
        value: bytes,
    ) -> SecretSetting:
        context = self._context(key)
        envelope = self._cipher.encrypt(value, context=context)
        updated_at = self._now()
        with self._session_factory.begin() as session:
            setting = session.get(EncryptedSetting, key, with_for_update=True)
            if (
                setting is None
                or setting.version != expected_version
                or (
                    setting.public_value is not None
                    and setting.public_value != _CLEARED_SECRET
                )
            ):
                raise ConcurrentSettingUpdate
            setting.public_value = None
            setting.key_id = envelope.key_id
            setting.nonce = envelope.nonce
            setting.ciphertext = envelope.ciphertext
            setting.version += 1
            setting.updated_at = updated_at
        return SecretSetting(
            key=key,
            value=value,
            version=expected_version + 1,
            updated_at=updated_at,
        )

    def get_secret(self, key: str) -> SecretSetting | None:
        with self._session_factory() as session:
            setting = session.scalar(
                select(EncryptedSetting).where(EncryptedSetting.key == key)
            )
            if setting is None:
                return None
            if (
                setting.public_value is not None
                or setting.key_id is None
                or setting.nonce is None
                or setting.ciphertext is None
            ):
                return None
            value = self._cipher.decrypt(
                EncryptedEnvelope(
                    key_id=setting.key_id,
                    nonce=setting.nonce,
                    ciphertext=setting.ciphertext,
                ),
                context=self._context(key),
            )
            return SecretSetting(
                key=key,
                value=value,
                version=setting.version,
                updated_at=setting.updated_at,
            )

    def get_status(self, key: str) -> SettingStatus | None:
        with self._session_factory() as session:
            row = session.execute(
                select(
                    EncryptedSetting.key,
                    EncryptedSetting.key_id,
                    EncryptedSetting.version,
                    EncryptedSetting.updated_at,
                ).where(EncryptedSetting.key == key)
            ).one_or_none()
            if row is None:
                return None
            return SettingStatus(
                key=row.key,
                configured=row.key_id is not None,
                version=row.version,
                updated_at=row.updated_at,
            )

    def delete_secret(self, key: str, *, expected_version: int) -> None:
        updated_at = self._now()
        with self._session_factory.begin() as session:
            setting = session.get(EncryptedSetting, key, with_for_update=True)
            if (
                setting is None
                or setting.version != expected_version
                or setting.public_value is not None
            ):
                raise ConcurrentSettingUpdate
            setting.public_value = dict(_CLEARED_SECRET)
            setting.key_id = None
            setting.nonce = None
            setting.ciphertext = None
            setting.version += 1
            setting.updated_at = updated_at

    def get_public(self, key: str) -> PublicSetting | None:
        with self._session_factory() as session:
            setting = session.get(EncryptedSetting, key)
            if (
                setting is None
                or setting.public_value is None
                or setting.public_value == _CLEARED_SECRET
            ):
                return None
            return PublicSetting(
                key=setting.key,
                value=setting.public_value,
                version=setting.version,
                updated_at=setting.updated_at,
            )

    def set_public(self, key: str, value: object) -> PublicSetting:
        self._context(key)
        updated_at = self._now()
        with self._session_factory.begin() as session:
            setting = session.get(EncryptedSetting, key, with_for_update=True)
            if setting is None:
                setting = EncryptedSetting(
                    key=key,
                    public_value=value,
                    key_id=None,
                    nonce=None,
                    ciphertext=None,
                    version=1,
                    updated_at=updated_at,
                )
                session.add(setting)
            elif setting.public_value is None:
                raise ConcurrentSettingUpdate
            else:
                setting.public_value = value
                setting.version += 1
                setting.updated_at = updated_at
            session.flush()
            return PublicSetting(
                key=setting.key,
                value=setting.public_value,
                version=setting.version,
                updated_at=setting.updated_at,
            )

    @staticmethod
    def _context(key: str) -> bytes:
        if not key or len(key) > 128:
            raise ValueError("setting key must be 1..128 characters")
        return f"sakuraplayer.encrypted_setting.v1:{key}".encode("utf-8")
