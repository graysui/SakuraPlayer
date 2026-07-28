from pathlib import Path

from sakuraplayer.identity.models import Base
from sakuraplayer.playback.models import MoviePlaybackState

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def test_task_111_model_has_exact_movie_playback_state_shape() -> None:
    assert MoviePlaybackState.__tablename__ == "movie_playback_state"
    assert MoviePlaybackState.metadata is Base.metadata
    assert set(Base.metadata.tables["movie_playback_state"].columns.keys()) == {
        "movie_id",
        "position_seconds",
        "duration_seconds",
        "completed",
        "version",
        "last_watched_at",
        "updated_at",
    }


def test_task_111_migration_is_linear_and_owns_only_progress_schema() -> None:
    path = BACKEND_ROOT / "alembic" / "versions" / "0019_playback_progress.py"
    source = path.read_text(encoding="utf-8")

    assert 'revision: str = "0019_playback_progress"' in source
    assert (
        'down_revision: Union[str, Sequence[str], None] = "0018_cache_lifecycle"'
        in source
    )
    for expected in (
        '"movie_playback_state"',
        "ck_movie_playback_position",
        "ck_movie_playback_duration",
        "ck_movie_playback_completed_position",
        "ck_movie_playback_version",
        'ondelete="CASCADE"',
    ):
        assert expected in source
    for unrelated in ('"playback_session"', '"playback_lease"', '"cache_job"'):
        assert unrelated not in source
