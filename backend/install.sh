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

validate_ipv4() {
  local value="$1"
  local octet
  [[ "$value" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ ]] || return 1
  [[ "$value" != "0.0.0.0" ]] || return 1
  IFS=. read -r -a octets <<<"$value"
  for octet in "${octets[@]}"; do
    ((10#$octet <= 255)) || return 1
  done
}

validate_port() {
  local value="$1"
  [[ "$value" =~ ^[0-9]+$ ]] || return 1
  ((10#$value >= 1 && 10#$value <= 65535))
}

generate_secret() {
  local byte_count="$1"
  openssl rand -base64 "$byte_count" | tr '+/' '-_' | tr -d '=\n'
}

prepare_data_dirs() {
  local path
  for path in \
    "$SCRIPT_DIR/data/postgres" \
    "$SCRIPT_DIR/data/catalog-images" \
    "$SCRIPT_DIR/data/provider-cache" \
    "$SCRIPT_DIR/data/app-logs"; do
    mkdir -p -- "$path"
  done
  if [[ -z "$(find "$SCRIPT_DIR/data/postgres" -mindepth 1 -print -quit 2>/dev/null)" ]]; then
    chown 999:999 "$SCRIPT_DIR/data/postgres" ||
      fail "data_permissions_invalid" "Could not prepare PostgreSQL data directory permissions"
  fi
}

read_env_value() {
  local name="$1"
  sed -nE "s/^${name}=([^[:space:]]*).*$/\1/p" "$ENV_FILE" | sed -n '1p'
}

repair_postgres_password() {
  local postgres_user postgres_db password
  postgres_user="$(read_env_value POSTGRES_USER)"
  postgres_db="$(read_env_value POSTGRES_DB)"
  postgres_user="${postgres_user:-sakuraplayer}"
  postgres_db="${postgres_db:-sakuraplayer}"
  [[ "$postgres_user" =~ ^[A-Za-z0-9_]+$ && "$postgres_db" =~ ^[A-Za-z0-9_]+$ ]] ||
    fail "postgres_config_invalid" "PostgreSQL database and user names are invalid"
  password="$(<"$SECRET_DIR/postgres_password.txt")"
  local compose=(docker compose --project-directory "$SCRIPT_DIR" --env-file "$ENV_FILE" -p sakuraplayer)
  "${compose[@]}" up -d --wait postgres >/dev/null 2>&1 ||
    fail "postgres_start_failed" "PostgreSQL did not become healthy"
  printf 'ALTER ROLE "%s" PASSWORD '\''%s'\'';\n' "$postgres_user" "$password" |
    "${compose[@]}" exec -T -u postgres postgres \
      psql -v ON_ERROR_STOP=1 -U "$postgres_user" -d "$postgres_db" >/dev/null 2>&1 ||
    fail "postgres_password_prepare_failed" "Could not synchronize the PostgreSQL password"
}

create_env_if_missing() {
  local version="$1"
  local image="docker.io/graysui/sakuraplayer-backend:$version"
  local publish_host="${SAKURAPLAYER_INSTALLER_PUBLISH_HOST:-127.0.0.1}"
  local api_port="${SAKURAPLAYER_INSTALLER_API_PORT:-8000}"

  if [[ -L "$ENV_FILE" || ( -e "$ENV_FILE" && ! -f "$ENV_FILE" ) ]]; then
    fail "env_unsafe_path" ".env must be a regular file"
  fi
  if [[ -f "$ENV_FILE" ]]; then
    chmod 600 "$ENV_FILE"
    printf 'Configuration ready: existing file preserved.\n'
    return
  fi

  validate_ipv4 "$publish_host" ||
    fail "network_host_invalid" "Publish host must be a valid IPv4 address other than 0.0.0.0"
  validate_port "$api_port" ||
    fail "network_port_invalid" "API port must be an integer from 1 to 65535"

  CURRENT_TEMP="$(mktemp "$SCRIPT_DIR/.env.tmp.XXXXXX")"
  sed -e 's/\r$//' \
    -e "s|^SAKURAPLAYER_BACKEND_IMAGE=.*$|SAKURAPLAYER_BACKEND_IMAGE=$image|" \
    -e "s|^SAKURAPLAYER_PUBLISH_HOST=.*$|SAKURAPLAYER_PUBLISH_HOST=$publish_host|" \
    -e "s|^SAKURAPLAYER_API_PORT=.*$|SAKURAPLAYER_API_PORT=$api_port|" \
    "$ENV_TEMPLATE" >"$CURRENT_TEMP"
  chmod 600 "$CURRENT_TEMP"
  grep -Fx "SAKURAPLAYER_BACKEND_IMAGE=$image" "$CURRENT_TEMP" >/dev/null ||
    fail "env_template_invalid" "Image setting is missing from .env.example"
  grep -Fx "SAKURAPLAYER_PUBLISH_HOST=$publish_host" "$CURRENT_TEMP" >/dev/null ||
    fail "env_template_invalid" "Publish host setting is missing from .env.example"
  grep -Fx "SAKURAPLAYER_API_PORT=$api_port" "$CURRENT_TEMP" >/dev/null ||
    fail "env_template_invalid" "API port setting is missing from .env.example"
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
  require_command find
  require_command chown

  require_regular_source "$COMPOSE_FILE" "docker-compose.yml"
  require_regular_source "$ENV_TEMPLATE" ".env.example"

  docker info >/dev/null 2>&1 ||
    fail "docker_unavailable" "Docker Engine is not available"
  docker compose version >/dev/null 2>&1 ||
    fail "compose_unavailable" "Docker Compose v2 is not available"

  local version
  version="$(resolve_version)"
  cd -- "$SCRIPT_DIR"
  prepare_data_dirs
  prepare_secrets
  create_env_if_missing "$version"

  local compose=(docker compose --env-file "$ENV_FILE" -p sakuraplayer)
  printf 'Validating Docker Compose configuration...\n'
  "${compose[@]}" config --quiet >/dev/null 2>&1 ||
    fail "compose_config_failed" "Docker Compose configuration is invalid"
  printf 'Pulling SakuraPlayer images...\n'
  "${compose[@]}" pull >/dev/null 2>&1 ||
    fail "compose_pull_failed" "SakuraPlayer images could not be pulled"
  printf 'Preparing PostgreSQL credentials...\n'
  repair_postgres_password
  printf 'Starting SakuraPlayer services...\n'
  "${compose[@]}" up -d --no-build --wait >/dev/null 2>&1 ||
    fail "compose_start_failed" "SakuraPlayer services did not become healthy"

  local publish_host api_port
  publish_host="$(sed -nE 's/^SAKURAPLAYER_PUBLISH_HOST=([^[:space:]]*).*$/\1/p' "$ENV_FILE" | sed -n '1p')"
  api_port="$(sed -nE 's/^SAKURAPLAYER_API_PORT=([^[:space:]]*).*$/\1/p' "$ENV_FILE" | sed -n '1p')"
  publish_host="${publish_host:-127.0.0.1}"
  api_port="${api_port:-8000}"
  printf 'SakuraPlayer backend is ready at http://%s:%s\n' "$publish_host" "$api_port"
  printf 'Bootstrap token file: %s\n' "$SECRET_DIR/bootstrap_token.txt"
}

main "$@"
