#!/usr/bin/env bash
set -Eeuo pipefail

umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.yml"
ENV_TEMPLATE="$SCRIPT_DIR/.env.example"
ENV_FILE="$SCRIPT_DIR/.env"
SECRET_DIR="$SCRIPT_DIR/secrets"
RELEASE_VERSION_FILE="$SCRIPT_DIR/.release-version"
PUBSPEC_FILE="$SCRIPT_DIR/../windows/pubspec.yaml"
CURRENT_TEMP=""

cleanup_temp() {
  if [[ -n "$CURRENT_TEMP" && -f "$CURRENT_TEMP" ]]; then
    rm -f -- "$CURRENT_TEMP"
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

require_regular_source() {
  local path="$1"
  local label="$2"
  if [[ -L "$path" || ! -f "$path" ]]; then
    fail "deployment_file_invalid" "$label must be a regular file"
  fi
}

resolve_version() {
  local version
  if [[ -e "$RELEASE_VERSION_FILE" || -L "$RELEASE_VERSION_FILE" ]]; then
    require_regular_source "$RELEASE_VERSION_FILE" ".release-version"
    version="$(<"$RELEASE_VERSION_FILE")"
  elif [[ -f "$PUBSPEC_FILE" && ! -L "$PUBSPEC_FILE" ]]; then
    version="$(
      sed -nE 's/^version:[[:space:]]*([0-9]+\.[0-9]+\.[0-9]+)\+[0-9]+[[:space:]]*$/\1/p' \
        "$PUBSPEC_FILE"
    )"
  else
    fail "release_version_missing" "No release version source is available"
  fi

  if [[ ! "$version" =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]]; then
    fail "release_version_invalid" "Release version must use canonical X.Y.Z syntax"
  fi
  printf '%s' "$version"
}

secret_is_valid() {
  local value="$1"
  local expected_length="$2"
  [[ ${#value} -eq "$expected_length" && "$value" =~ ^[A-Za-z0-9_-]+$ ]]
}

value_is_reused() {
  local candidate="$1"
  shift
  local existing
  for existing in "$@"; do
    if [[ "$candidate" == "$existing" ]]; then
      return 0
    fi
  done
  return 1
}

generate_secret() {
  local byte_count="$1"
  openssl rand -base64 "$byte_count" | tr '+/' '-_' | tr -d '=\n'
}

create_env_if_missing() {
  local version="$1"
  local image="docker.io/graysui/sakuraplayer-backend:$version"

  if [[ -L "$ENV_FILE" || ( -e "$ENV_FILE" && ! -f "$ENV_FILE" ) ]]; then
    fail "env_unsafe_path" ".env must be a regular file"
  fi
  if [[ -f "$ENV_FILE" ]]; then
    chmod 600 "$ENV_FILE"
    printf 'Configuration ready: existing file preserved.\n'
    return
  fi

  CURRENT_TEMP="$(mktemp "$SCRIPT_DIR/.env.tmp.XXXXXX")"
  sed -e 's/\r$//' \
    -e "s|^SAKURAPLAYER_BACKEND_IMAGE=.*$|SAKURAPLAYER_BACKEND_IMAGE=$image|" \
    "$ENV_TEMPLATE" >"$CURRENT_TEMP"
  chmod 600 "$CURRENT_TEMP"
  grep -Fx "SAKURAPLAYER_BACKEND_IMAGE=$image" "$CURRENT_TEMP" >/dev/null ||
    fail "env_template_invalid" "Image setting is missing from .env.example"
  grep -Fx 'SAKURAPLAYER_PUBLISH_HOST=127.0.0.1' "$CURRENT_TEMP" >/dev/null ||
    fail "env_template_invalid" "Loopback default is missing from .env.example"
  if ! ln "$CURRENT_TEMP" "$ENV_FILE" 2>/dev/null; then
    fail "env_create_race" ".env appeared during installation; retry after review"
  fi
  rm -f -- "$CURRENT_TEMP"
  CURRENT_TEMP=""
  printf 'Configuration ready: release defaults created.\n'
}

prepare_secrets() {
  local names=(
    postgres_password.txt
    settings_key.txt
    token_key.txt
    playback_key.txt
    bootstrap_token.txt
  )
  local byte_counts=(32 32 48 48 48)
  local encoded_lengths=(43 43 64 64 64)
  local values=()
  local index path value size attempt

  if [[ -L "$SECRET_DIR" || ( -e "$SECRET_DIR" && ! -d "$SECRET_DIR" ) ]]; then
    fail "secret_unsafe_path" "secrets must be a real directory"
  fi
  mkdir -p -- "$SECRET_DIR"
  chmod 700 "$SECRET_DIR"

  local lock_file="$SECRET_DIR/.install.lock"
  if [[ -L "$lock_file" || ( -e "$lock_file" && ! -f "$lock_file" ) ]]; then
    fail "secret_unsafe_path" "Installer lock must be a regular file"
  fi
  : >>"$lock_file"
  chmod 600 "$lock_file"
  exec 9<>"$lock_file"
  flock -n 9 || fail "install_locked" "Another installation is already running"

  for index in "${!names[@]}"; do
    path="$SECRET_DIR/${names[$index]}"
    if [[ -L "$path" || ( -e "$path" && ! -f "$path" ) ]]; then
      fail "secret_unsafe_path" "${names[$index]} must be a regular file"
    fi
    if [[ ! -f "$path" ]]; then
      continue
    fi

    size="$(wc -c <"$path" | tr -d '[:space:]')"
    value="$(<"$path")"
    if [[ "$size" != "${encoded_lengths[$index]}" ]] ||
      ! secret_is_valid "$value" "${encoded_lengths[$index]}"; then
      fail "secret_invalid" "${names[$index]} has an invalid format"
    fi
    if value_is_reused "$value" "${values[@]}"; then
      fail "secret_reused" "Secret purposes must use different material"
    fi
    chmod 600 "$path"
    values+=("$value")
  done

  for index in "${!names[@]}"; do
    path="$SECRET_DIR/${names[$index]}"
    if [[ -f "$path" ]]; then
      continue
    fi

    value=""
    for attempt in 1 2 3 4 5; do
      value="$(generate_secret "${byte_counts[$index]}")"
      if secret_is_valid "$value" "${encoded_lengths[$index]}" &&
        ! value_is_reused "$value" "${values[@]}"; then
        break
      fi
      value=""
    done
    if [[ -z "$value" ]]; then
      fail "secret_generation_failed" "Could not generate independent secret material"
    fi

    CURRENT_TEMP="$(mktemp "$SECRET_DIR/.${names[$index]}.tmp.XXXXXX")"
    printf '%s' "$value" >"$CURRENT_TEMP"
    chmod 600 "$CURRENT_TEMP"
    if ! ln "$CURRENT_TEMP" "$path" 2>/dev/null; then
      fail "secret_create_race" "${names[$index]} appeared during installation"
    fi
    rm -f -- "$CURRENT_TEMP"
    CURRENT_TEMP=""
    values+=("$value")
  done
  printf 'Secrets ready: valid files preserved and missing files created.\n'
}

main() {
  require_command docker
  require_command openssl
  require_command flock
  require_command mktemp
  require_command sed
  require_command tr
  require_command wc
  require_command ln

  require_regular_source "$COMPOSE_FILE" "docker-compose.yml"
  require_regular_source "$ENV_TEMPLATE" ".env.example"

  docker info >/dev/null 2>&1 ||
    fail "docker_unavailable" "Docker Engine is not available"
  docker compose version >/dev/null 2>&1 ||
    fail "compose_unavailable" "Docker Compose v2 is not available"

  local version
  version="$(resolve_version)"
  cd -- "$SCRIPT_DIR"
  prepare_secrets
  create_env_if_missing "$version"

  local compose=(docker compose --env-file "$ENV_FILE" -p sakuraplayer)
  printf 'Validating Docker Compose configuration...\n'
  "${compose[@]}" config --quiet >/dev/null 2>&1 ||
    fail "compose_config_failed" "Docker Compose configuration is invalid"
  printf 'Pulling SakuraPlayer images...\n'
  "${compose[@]}" pull >/dev/null 2>&1 ||
    fail "compose_pull_failed" "SakuraPlayer images could not be pulled"
  printf 'Starting SakuraPlayer services...\n'
  "${compose[@]}" up -d --no-build --wait >/dev/null 2>&1 ||
    fail "compose_start_failed" "SakuraPlayer services did not become healthy"

  printf 'SakuraPlayer backend is ready at http://127.0.0.1:8000\n'
  printf 'Bootstrap token file: %s\n' "$SECRET_DIR/bootstrap_token.txt"
}

main "$@"
