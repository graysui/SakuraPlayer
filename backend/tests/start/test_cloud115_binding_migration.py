from pathlib import Path

from sakuraplayer.cloud_cache.models import Cloud115Binding
from sakuraplayer.identity.models import Base

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def test_cloud115_binding_model_is_registered() -> None:
    assert Cloud115Binding.__tablename__ == "cloud115_binding"
    assert Cloud115Binding.metadata is Base.metadata
    columns = Base.metadata.tables["cloud115_binding"].columns
    assert set(columns.keys()) == {
        "id",
        "singleton_key",
        "account_key",
        "display_name",
        "cookie_setting_key",
        "login_app",
        "cache_root_cid",
        "status",
        "credential_version",
        "last_verified_at",
        "created_at",
        "updated_at",
    }


def test_task_102_migration_is_linear_and_owns_binding_schema() -> None:
    path = BACKEND_ROOT / "alembic" / "versions" / "0014_cloud115_binding.py"
    source = path.read_text(encoding="utf-8")
    assert 'revision: str = "0014_cloud115_binding"' in source
    assert (
        "down_revision: Union[str, Sequence[str], None] = "
        '"0013_events_settings_diagnostics"'
    ) in source
    for expected in (
        '"cloud115_binding"',
        "uq_cloud115_binding_singleton_key",
        "ck_cloud115_binding_cookie_key",
        "ck_cloud115_binding_status",
        "ck_cloud115_binding_credential_version",
        '"encrypted_setting.key"',
    ):
        assert expected in source
