#!/usr/bin/env bash
set -Eeuo pipefail

umask 077

REPOSITORY="graysui/SakuraPlayer"
RELEASES_LATEST_URL="https://github.com/${REPOSITORY}/releases/latest"
CURRENT_TEMP_DIR=""

cleanup_temp() {
  if [[ -n "$CURRENT_TEMP_DIR" && -d "$CURRENT_TEMP_DIR" ]]; then
    rm -rf -- "$CURRENT_TEMP_DIR"
  fi
}

trap cleanup_temp EXIT

fail() {
  local code="$1"
  local message="$2"
  printf 'ERROR %s: %s\n' "$code" "$message" >&2
  exit 1
}

require_command() {
  local name="$1"
  command -v "$name" >/dev/null 2>&1 ||
    fail "dependency_missing" "Required command is unavailable: $name"
}

resolve_latest_tag() {
  local release_url tag
  release_url="$(
    curl -fsSIL --proto '=https' --tlsv1.2 \
      -o /dev/null -w '%{url_effective}' "$RELEASES_LATEST_URL"
  )"
  release_url="${release_url%/}"
  if [[ ! "$release_url" =~ ^https://github\.com/graysui/SakuraPlayer/releases/tag/(v[0-9]+\.[0-9]+\.[0-9]+)$ ]]; then
    fail "release_version_invalid" "GitHub latest release did not resolve to a canonical vX.Y.Z tag"
  fi
  tag="${BASH_REMATCH[1]}"
  printf '%s' "$tag"
}

download_and_run() {
  local tag="$1"
  shift
  local version="${tag#v}"
  local archive_name="SakuraPlayer-Docker-${version}.tar.gz"
  local archive_path="$CURRENT_TEMP_DIR/$archive_name"
  local extract_dir="$CURRENT_TEMP_DIR/extracted"
  local package_dir="$extract_dir/SakuraPlayer-Docker-${version}"
  local download_url="https://github.com/${REPOSITORY}/releases/download/${tag}/${archive_name}"

  printf 'Downloading SakuraPlayer Docker release %s...\n' "$version"
  curl -fL --proto '=https' --tlsv1.2 -o "$archive_path" "$download_url" ||
    fail "release_download_failed" "SakuraPlayer Docker release could not be downloaded"

  local archive_entries entry
  archive_entries="$(tar -tzf "$archive_path")" ||
    fail "release_archive_invalid" "SakuraPlayer Docker release archive could not be read"
  while IFS= read -r entry; do
    case "$entry" in
      "SakuraPlayer-Docker-${version}"|"SakuraPlayer-Docker-${version}"/*) ;;
      *) fail "release_archive_invalid" "SakuraPlayer Docker release archive has an invalid path" ;;
    esac
    case "$entry" in
      /*|../*|*/../*|*/..|*/./*|*/.)
        fail "release_archive_invalid" "SakuraPlayer Docker release archive has an unsafe path"
        ;;
    esac
  done <<<"$archive_entries"

  mkdir -p -- "$extract_dir"
  tar -xzf "$archive_path" -C "$extract_dir" ||
    fail "release_archive_invalid" "SakuraPlayer Docker release archive could not be extracted"
  [[ -L "$package_dir" || ! -d "$package_dir" ]] &&
    fail "release_archive_invalid" "SakuraPlayer Docker release archive has an invalid layout"
  local required_file
  for required_file in install.sh docker-compose.yml .env.example .release-version; do
    if [[ -L "$package_dir/$required_file" || ! -f "$package_dir/$required_file" ]]; then
      fail "release_archive_invalid" "SakuraPlayer Docker release archive has an invalid layout"
    fi
  done

  printf 'Starting SakuraPlayer Docker services...\n'
  /bin/bash "$package_dir/install.sh" "$@"
}

main() {
  require_command curl
  require_command mktemp
  require_command tar
  require_command rm

  CURRENT_TEMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/sakuraplayer-install.XXXXXX")"
  local tag
  tag="$(resolve_latest_tag)"
  download_and_run "$tag" "$@"
}

main "$@"
