from __future__ import annotations

import hashlib
import importlib.util
import re
import tarfile
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
BUNDLE_TOOL = REPOSITORY_ROOT / "tools" / "release" / "build_docker_bundle.py"


def _load_bundle_tool():
    assert BUNDLE_TOOL.is_file(), "Docker bundle builder is missing"
    spec = importlib.util.spec_from_file_location("docker_bundle", BUNDLE_TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_docker_release_bundle_has_strict_allowlist_and_checksum(
    tmp_path: Path,
) -> None:
    module = _load_bundle_tool()

    result = module.build_bundle(
        version="1.2.3", repository_root=REPOSITORY_ROOT, output_dir=tmp_path
    )

    assert result.archive.name == "SakuraPlayer-Docker-1.2.3.tar.gz"
    assert result.checksum.name == f"{result.archive.name}.sha256"
    digest = hashlib.sha256(result.archive.read_bytes()).hexdigest()
    assert result.checksum.read_text(encoding="ascii") == (
        f"{digest}  {result.archive.name}\n"
    )
    with tarfile.open(result.archive, "r:gz") as archive:
        members = {member.name: member for member in archive.getmembers()}
        root = "SakuraPlayer-Docker-1.2.3"
        expected = {
            f"{root}/docker-compose.yml",
            f"{root}/.env.example",
            f"{root}/.release-version",
            f"{root}/install.sh",
            f"{root}/install-latest.sh",
            f"{root}/README.md",
            f"{root}/LICENSE",
            f"{root}/THIRD_PARTY_NOTICES.md",
        }
        assert set(members) == expected
        assert members[f"{root}/install.sh"].mode == 0o755
        assert members[f"{root}/install-latest.sh"].mode == 0o755
        assert all(
            member.mode == 0o644
            for name, member in members.items()
            if name not in {f"{root}/install.sh", f"{root}/install-latest.sh"}
        )
        version_file = archive.extractfile(members[f"{root}/.release-version"])
        assert version_file is not None
        assert version_file.read() == b"1.2.3\n"
        readme_file = archive.extractfile(members[f"{root}/README.md"])
        assert readme_file is not None
        readme = readme_file.read().decode("utf-8")
        assert "./install.sh" in readme
        assert "127.0.0.1:8000" in readme
        assert not re.search(r"windows|pubspec|harmony|android|ios", readme, re.I)
        assert not any(
            re.search(r"(^|/)(\.env|secrets)(/|$)", name) for name in members
        )


def test_docker_release_bundle_is_reproducible(tmp_path: Path) -> None:
    module = _load_bundle_tool()

    first = module.build_bundle(
        version="1.2.3",
        repository_root=REPOSITORY_ROOT,
        output_dir=tmp_path / "first",
    )
    second = module.build_bundle(
        version="1.2.3",
        repository_root=REPOSITORY_ROOT,
        output_dir=tmp_path / "second",
    )

    assert first.archive.read_bytes() == second.archive.read_bytes()
    assert first.checksum.read_text(encoding="ascii") == second.checksum.read_text(
        encoding="ascii"
    )


@pytest.mark.parametrize("version", ["v1.2.3", "1.2", "01.2.3", "latest"])
def test_docker_release_bundle_rejects_noncanonical_version(
    tmp_path: Path, version: str
) -> None:
    module = _load_bundle_tool()

    with pytest.raises(ValueError, match="version"):
        module.build_bundle(
            version=version, repository_root=REPOSITORY_ROOT, output_dir=tmp_path
        )
