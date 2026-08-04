from __future__ import annotations

import argparse
import os
import re
from pathlib import Path
from typing import NamedTuple

TAG_PATTERN = re.compile(r"^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
PUBSPEC_VERSION_PATTERN = re.compile(
    r"^version:\s*(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)\+([1-9]\d*)\s*$",
    re.MULTILINE,
)


class ReleaseVersion(NamedTuple):
    semver: str
    build_number: str
    artifact_version: str
    archive_name: str
    installer_name: str
    docker_archive_name: str


def validate_release_version(*, tag: str, pubspec_path: Path) -> ReleaseVersion:
    tag_match = TAG_PATTERN.fullmatch(tag)
    if tag_match is None:
        raise ValueError("release tag must use canonical vX.Y.Z syntax")

    pubspec = pubspec_path.read_text(encoding="utf-8")
    version_match = PUBSPEC_VERSION_PATTERN.search(pubspec)
    if version_match is None:
        raise ValueError("pubspec version must use canonical X.Y.Z+B syntax")

    tag_version = ".".join(tag_match.groups())
    pubspec_version = ".".join(version_match.groups()[:3])
    if tag_version != pubspec_version:
        raise ValueError(
            f"release tag {tag_version} does not match pubspec version {pubspec_version}"
        )

    build_number = version_match.group(4)
    artifact_version = f"{pubspec_version}-{build_number}"
    return ReleaseVersion(
        semver=pubspec_version,
        build_number=build_number,
        artifact_version=artifact_version,
        archive_name=f"SakuraPlayer-Windows-{artifact_version}.zip",
        installer_name=f"SakuraPlayer-Windows-{artifact_version}-Setup.exe",
        docker_archive_name=f"SakuraPlayer-Docker-{pubspec_version}.tar.gz",
    )


def _write_github_output(path: Path, version: ReleaseVersion) -> None:
    values = {
        "semver": version.semver,
        "build_number": version.build_number,
        "artifact_version": version.artifact_version,
        "archive_name": version.archive_name,
        "installer_name": version.installer_name,
        "docker_archive_name": version.docker_archive_name,
    }
    with path.open("a", encoding="utf-8", newline="\n") as output:
        for name, value in values.items():
            output.write(f"{name}={value}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a SakuraPlayer release tag.")
    parser.add_argument("--tag", default=os.environ.get("GITHUB_REF_NAME"))
    parser.add_argument(
        "--pubspec",
        type=Path,
        default=Path("windows/pubspec.yaml"),
    )
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()

    if not args.tag:
        parser.error("--tag or GITHUB_REF_NAME is required")

    version = validate_release_version(tag=args.tag, pubspec_path=args.pubspec)
    if args.github_output is not None:
        _write_github_output(args.github_output, version)
    print(f"Validated SakuraPlayer release {version.semver} ({version.archive_name})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
