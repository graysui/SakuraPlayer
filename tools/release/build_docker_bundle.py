from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import re
import tarfile
from pathlib import Path
from typing import NamedTuple

VERSION_PATTERN = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


class BundleResult(NamedTuple):
    archive: Path
    checksum: Path


def _bundle_files(repository_root: Path, version: str) -> dict[str, bytes]:
    sources = {
        "docker-compose.yml": repository_root / "backend" / "docker-compose.yml",
        ".env.example": repository_root / "backend" / ".env.example",
        "install.sh": repository_root / "backend" / "install.sh",
        "install-latest.sh": repository_root / "backend" / "install-latest.sh",
        "README.md": repository_root / "backend" / "README.docker.md",
        "LICENSE": repository_root / "LICENSE",
        "THIRD_PARTY_NOTICES.md": repository_root / "THIRD_PARTY_NOTICES.md",
    }
    missing = [str(path) for path in sources.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"required deployment files are missing: {missing}")
    files = {name: path.read_bytes() for name, path in sources.items()}
    files[".release-version"] = f"{version}\n".encode("ascii")
    return files


def _write_archive(path: Path, *, version: str, files: dict[str, bytes]) -> None:
    root = f"SakuraPlayer-Docker-{version}"
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("wb") as raw_output:
        with gzip.GzipFile(
            fileobj=raw_output, mode="wb", filename="", mtime=0
        ) as zipped:
            with tarfile.open(
                fileobj=zipped, mode="w", format=tarfile.PAX_FORMAT
            ) as archive:
                for name in sorted(files):
                    data = files[name]
                    member = tarfile.TarInfo(f"{root}/{name}")
                    member.size = len(data)
                    member.mode = (
                        0o755 if name in {"install.sh", "install-latest.sh"} else 0o644
                    )
                    member.mtime = 0
                    member.uid = 0
                    member.gid = 0
                    member.uname = ""
                    member.gname = ""
                    archive.addfile(member, io.BytesIO(data))
    temporary.replace(path)


def build_bundle(
    *, version: str, repository_root: Path, output_dir: Path
) -> BundleResult:
    if VERSION_PATTERN.fullmatch(version) is None:
        raise ValueError("version must use canonical X.Y.Z syntax")

    repository_root = repository_root.resolve(strict=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_dir = output_dir.resolve(strict=True)
    archive = output_dir / f"SakuraPlayer-Docker-{version}.tar.gz"
    checksum = archive.with_name(f"{archive.name}.sha256")
    files = _bundle_files(repository_root, version)
    _write_archive(archive, version=version, files=files)

    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    checksum.write_text(f"{digest}  {archive.name}\n", encoding="ascii", newline="\n")
    return BundleResult(archive=archive, checksum=checksum)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the SakuraPlayer Linux Docker deployment bundle."
    )
    parser.add_argument("--version", required=True)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    result = build_bundle(
        version=args.version,
        repository_root=args.repository_root,
        output_dir=args.output_dir,
    )
    print(f"Created {result.archive.name} and {result.checksum.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
