from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


class AuthenticationError(RuntimeError):
    code = "authentication_required"


class BootstrapTokenInvalid(RuntimeError):
    code = "bootstrap_token_invalid"


class BootstrapAlreadyCompleted(RuntimeError):
    code = "bootstrap_already_completed"


class InvalidCredentials(RuntimeError):
    code = "invalid_credentials"


class IdentityValidationError(RuntimeError):
    code = "validation_failed"


class RefreshTokenInvalid(RuntimeError):
    code = "refresh_token_invalid"


class RefreshTokenReused(RuntimeError):
    code = "refresh_token_reused"


class SessionRevoked(RuntimeError):
    code = "session_revoked"


@dataclass(frozen=True)
class AccessClaims:
    admin_id: uuid.UUID
    session_id: uuid.UUID
    session_epoch: int
    expires_at: datetime


@dataclass(frozen=True)
class RefreshClaims:
    admin_id: uuid.UUID
    session_id: uuid.UUID
    issued_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    access_expires_at: datetime
    refresh_expires_at: datetime
    token_type: str = "Bearer"


@dataclass(frozen=True)
class CurrentAdmin:
    admin_id: uuid.UUID
    username: str
    session_id: uuid.UUID
    client_instance_id: uuid.UUID
    session_epoch: int


@dataclass(frozen=True)
class ClientCleanupSignal:
    client_instance_id: uuid.UUID
    clear_tokens: bool = True
    clear_subtitle_cache: bool = True
