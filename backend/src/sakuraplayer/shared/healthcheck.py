from __future__ import annotations

from sakuraplayer.shared.config import StartupConfigurationError, load_settings
from sakuraplayer.shared.schema_guard import SchemaGuardError
from sakuraplayer.shared.runtime import require_ready


def main() -> int:
    try:
        settings = load_settings()
        require_ready(settings)
    except (StartupConfigurationError, SchemaGuardError):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
