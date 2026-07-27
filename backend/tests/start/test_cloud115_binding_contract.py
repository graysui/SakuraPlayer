from __future__ import annotations

from typing import Any

from sakuraplayer.api.app import create_app


class _Service:
    def __getattr__(self, name: str) -> Any:
        def unavailable(*_args: Any, **_kwargs: Any) -> None:
            raise AssertionError(f"placeholder invoked: {name}")

        return unavailable


def test_actual_openapi_exposes_authenticated_cloud115_contract() -> None:
    service = _Service()
    app = create_app(
        readiness_probe=lambda: True,
        identity_service=service,  # type: ignore[arg-type]
        cloud115_binding_service=service,  # type: ignore[arg-type]
        cloud115_qr_service=service,  # type: ignore[arg-type]
    )
    schema = app.openapi()
    assert {
        "/api/v1/cloud115/binding",
        "/api/v1/cloud115/qr-sessions",
        "/api/v1/cloud115/qr-sessions/{qr_session_id}",
        "/api/v1/cloud115/qr-sessions/{qr_session_id}/confirm",
    } <= set(schema["paths"])
    assert set(
        schema["paths"]["/api/v1/cloud115/qr-sessions"]["post"]["responses"]
    ) >= {
        "201",
        "429",
        "502",
        "503",
    }
    confirm = schema["paths"]["/api/v1/cloud115/qr-sessions/{qr_session_id}/confirm"][
        "post"
    ]
    assert set(confirm["responses"]) >= {"200", "404", "409", "429", "502", "503"}
    qr_schema = schema["components"]["schemas"]["QrSessionOutput"]["properties"]
    for forbidden in ("token", "uid", "sign", "cookie", "account_key"):
        assert forbidden not in qr_schema
    assert qr_schema["status"]["enum"] == [
        "waiting",
        "scanned",
        "confirmed",
        "expired",
        "canceled",
    ]
    binding_schema = schema["components"]["schemas"]["Cloud115BindingOutput"]
    assert set(binding_schema["required"]) == {"bound", "status", "cache_root_ready"}
    assert binding_schema["properties"]["status"]["enum"] == [
        "unbound",
        "active",
        "expired",
        "unavailable",
        "detached",
    ]
