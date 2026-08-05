#!/usr/bin/env bash
set -Eeuo pipefail

umask 077

REPOSITORY="graysui/SakuraPlayer"
RELEASES_LATEST_URL="https://github.com/${REPOSITORY}/releases/latest"
CURRENT_TEMP_DIR=""
TARGET_DIR=""
SAKURAPLAYER_INSTALLER_PUBLISH_HOST=""
SAKURAPLAYER_INSTALLER_API_PORT=""
NETWORK_CONFIG_SELECTED=0

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

resolve_target_dir() {
  local requested_dir="${SAKURAPLAYER_INSTALL_DIR:-$PWD}"
  if [[ -L "$requested_dir" || ! -d "$requested_dir" ]]; then
    fail "install_dir_invalid" "Installation directory must be an existing real directory"
  fi
  TARGET_DIR="$(cd -- "$requested_dir" && pwd -P)"
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

select_network_config() {
  local host port current_host current_port
  if [[ -e "$TARGET_DIR/.env" || -L "$TARGET_DIR/.env" ]]; then
    if [[ -L "$TARGET_DIR/.env" || ! -f "$TARGET_DIR/.env" ]]; then
      fail "install_dir_unsafe" "Installation .env path is unsafe"
    fi
    current_host="$(sed -nE 's/^SAKURAPLAYER_PUBLISH_HOST=([^[:space:]]*).*$/\1/p' "$TARGET_DIR/.env" | sed -n '1p')"
    current_port="$(sed -nE 's/^SAKURAPLAYER_API_PORT=([^[:space:]]*).*$/\1/p' "$TARGET_DIR/.env" | sed -n '1p')"
    host="${current_host:-127.0.0.1}"
    port="${current_port:-8000}"
  else
    host="${SAKURAPLAYER_INSTALLER_PUBLISH_HOST:-127.0.0.1}"
    port="${SAKURAPLAYER_INSTALLER_API_PORT:-8000}"
    if [[ -t 0 || -t 1 ]] && [[ -r /dev/tty ]]; then
      printf 'SakuraPlayer first-install network configuration\n' >/dev/tty
      printf 'Publish host [ %s ]: ' "$host" >/dev/tty
      IFS= read -r host </dev/tty || host=""
      host="${host:-127.0.0.1}"
      printf 'API port [ %s ]: ' "$port" >/dev/tty
      IFS= read -r port </dev/tty || port=""
      port="${port:-8000}"
    fi
    NETWORK_CONFIG_SELECTED=1
  fi

  validate_ipv4 "$host" ||
    fail "network_host_invalid" "Publish host must be a valid IPv4 address other than 0.0.0.0"
  validate_port "$port" ||
    fail "network_port_invalid" "API port must be an integer from 1 to 65535"
  SAKURAPLAYER_INSTALLER_PUBLISH_HOST="$host"
  SAKURAPLAYER_INSTALLER_API_PORT="$port"
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

  local package_file package_path target_path mode
  local package_files=(
    docker-compose.yml
    .env.example
    .release-version
    install.sh
    README.md
    LICENSE
    THIRD_PARTY_NOTICES.md
  )
  if [[ -e "$package_dir/install-latest.sh" || -L "$package_dir/install-latest.sh" ]]; then
    package_files+=(install-latest.sh)
  elif [[ -L "$TARGET_DIR/install-latest.sh" || ( -e "$TARGET_DIR/install-latest.sh" && ! -f "$TARGET_DIR/install-latest.sh" ) ]]; then
    fail "install_dir_unsafe" "Installation directory contains an unsafe deployment file"
  fi
  for package_file in "${package_files[@]}"; do
    package_path="$package_dir/$package_file"
    target_path="$TARGET_DIR/$package_file"
    if [[ -L "$package_path" || ! -f "$package_path" ]]; then
      fail "release_archive_invalid" "SakuraPlayer Docker release archive has an invalid layout"
    fi
    if [[ -L "$target_path" || ( -e "$target_path" && ! -f "$target_path" ) ]]; then
      fail "install_dir_unsafe" "Installation directory contains an unsafe deployment file"
    fi
  done
  for package_file in "${package_files[@]}"; do
    package_path="$package_dir/$package_file"
    target_path="$TARGET_DIR/$package_file"
    cp -- "$package_path" "$target_path"
    mode=644
    if [[ "$package_file" == "install.sh" || "$package_file" == "install-latest.sh" ]]; then
      mode=755
    fi
    chmod "$mode" "$target_path"
  done

  prepare_target_env "$version"
  recover_running_secrets
  prepare_data_bind_mounts

  printf 'Installing SakuraPlayer files to %s\n' "$TARGET_DIR"
  printf 'Starting SakuraPlayer Docker services...\n'
  if /bin/bash "$TARGET_DIR/install.sh" "$@"; then
    return 0
  fi
  printf 'Repairing PostgreSQL credentials for the existing database...\n'
  repair_postgres_password ||
    fail "postgres_password_repair_failed" "Could not synchronize the PostgreSQL password with the local secret"
  SAKURAPLAYER_INSTALLER_PUBLISH_HOST="$SAKURAPLAYER_INSTALLER_PUBLISH_HOST" \
    SAKURAPLAYER_INSTALLER_API_PORT="$SAKURAPLAYER_INSTALLER_API_PORT" \
    /bin/bash "$TARGET_DIR/install.sh" "$@"
}

prepare_target_env() {
  local version="$1"
  local env_file="$TARGET_DIR/.env"
  local source_file="$env_file"
  local temporary

  if [[ "$NETWORK_CONFIG_SELECTED" != 1 ]]; then
    return
  fi
  if [[ -L "$env_file" || ( -e "$env_file" && ! -f "$env_file" ) ]]; then
    fail "install_dir_unsafe" "Installation .env path is unsafe"
  fi
  if [[ ! -f "$env_file" ]]; then
    source_file="$TARGET_DIR/.env.example"
  fi
  temporary="$(mktemp "$TARGET_DIR/.env.tmp.XXXXXX")"
  sed -e 's/\r$//' \
    -e "s|^SAKURAPLAYER_BACKEND_IMAGE=.*$|SAKURAPLAYER_BACKEND_IMAGE=docker.io/graysui/sakuraplayer-backend:$version|" \
    -e "s|^SAKURAPLAYER_PUBLISH_HOST=.*$|SAKURAPLAYER_PUBLISH_HOST=$SAKURAPLAYER_INSTALLER_PUBLISH_HOST|" \
    -e "s|^SAKURAPLAYER_API_PORT=.*$|SAKURAPLAYER_API_PORT=$SAKURAPLAYER_INSTALLER_API_PORT|" \
    "$source_file" >"$temporary"
  chmod 600 "$temporary"
  mv -f -- "$temporary" "$env_file"
}

prepare_data_bind_mounts() {
  local override_file="$TARGET_DIR/docker-compose.override.yml"
  local temporary
  if [[ -L "$override_file" || ( -e "$override_file" && ! -f "$override_file" ) ]]; then
    fail "install_dir_unsafe" "Installation Compose override path is unsafe"
  fi
  mkdir -p -- \
    "$TARGET_DIR/data/postgres" \
    "$TARGET_DIR/data/catalog-images" \
    "$TARGET_DIR/data/provider-cache" \
    "$TARGET_DIR/data/app-logs"
  migrate_named_volumes
  if grep -Fq './data/postgres:/var/lib/postgresql/data' "$TARGET_DIR/docker-compose.yml" &&
    grep -Fq './data/catalog-images:/var/lib/sakuraplayer/catalog-images' "$TARGET_DIR/docker-compose.yml" &&
    grep -Fq './data/provider-cache:/var/lib/sakuraplayer/provider-cache' "$TARGET_DIR/docker-compose.yml" &&
    grep -Fq './data/app-logs:/var/log/sakuraplayer' "$TARGET_DIR/docker-compose.yml"; then
    return
  fi
  if [[ -f "$override_file" ]]; then
    return
  fi
  temporary="$(mktemp "$TARGET_DIR/.docker-compose.override.yml.tmp.XXXXXX")"
  printf '%s\n' \
    'services:' \
    '  postgres:' \
    '    volumes:' \
    '      - ./data/postgres:/var/lib/postgresql/data' \
    '  api:' \
    '    volumes:' \
    '      - ./data/catalog-images:/var/lib/sakuraplayer/catalog-images' \
    '      - ./data/provider-cache:/var/lib/sakuraplayer/provider-cache' \
    '      - ./data/app-logs:/var/log/sakuraplayer' \
    '  worker:' \
    '    volumes:' \
    '      - ./data/catalog-images:/var/lib/sakuraplayer/catalog-images' \
    '      - ./data/provider-cache:/var/lib/sakuraplayer/provider-cache' \
    '      - ./data/app-logs:/var/log/sakuraplayer' \
    '  scheduler:' \
    '    volumes:' \
    '      - ./data/catalog-images:/var/lib/sakuraplayer/catalog-images' \
    '      - ./data/provider-cache:/var/lib/sakuraplayer/provider-cache' \
    '      - ./data/app-logs:/var/log/sakuraplayer' \
    >"$temporary"
  chmod 644 "$temporary"
  mv -f -- "$temporary" "$override_file"
}

migrate_named_volumes() {
  local volume_name target_dir
  local volumes=(db-data catalog-images provider-cache app-logs)
  local containers
  command -v docker >/dev/null 2>&1 || return 0
  containers="$(docker ps -aq --filter 'label=com.docker.compose.project=sakuraplayer' 2>/dev/null || true)"
  if [[ -n "$containers" ]]; then
    docker compose --project-directory "$TARGET_DIR" -p sakuraplayer down >/dev/null 2>&1 || true
  fi
  for volume_name in "${volumes[@]}"; do
    if [[ "$volume_name" == "db-data" ]]; then
      target_dir="$TARGET_DIR/data/postgres"
    else
      target_dir="$TARGET_DIR/data/$volume_name"
    fi
    if ! docker volume inspect "sakuraplayer_$volume_name" >/dev/null 2>&1; then
      continue
    fi
    if find "$target_dir" -mindepth 1 -print -quit 2>/dev/null | grep -q .; then
      continue
    fi
    docker run --rm \
      --user 0:0 \
      -v "sakuraplayer_$volume_name:/from:ro" \
      -v "$target_dir:/to" \
      postgres:17.5 \
      sh -c 'cp -a /from/. /to/' >/dev/null 2>&1 ||
      fail "volume_migration_failed" "Could not move Docker volume $volume_name into the installation directory"
  done
}

repair_postgres_password() {
  local env_file="$TARGET_DIR/.env"
  local postgres_user postgres_db password
  postgres_user="$(sed -nE 's/^POSTGRES_USER=([^[:space:]]*).*$/\1/p' "$env_file" | sed -n '1p')"
  postgres_db="$(sed -nE 's/^POSTGRES_DB=([^[:space:]]*).*$/\1/p' "$env_file" | sed -n '1p')"
  postgres_user="${postgres_user:-sakuraplayer}"
  postgres_db="${postgres_db:-sakuraplayer}"
  [[ "$postgres_user" =~ ^[A-Za-z0-9_]+$ && "$postgres_db" =~ ^[A-Za-z0-9_]+$ ]] || return 1
  password="$(<"$TARGET_DIR/secrets/postgres_password.txt")"
  local compose=(docker compose --project-directory "$TARGET_DIR" --env-file "$env_file" -p sakuraplayer)
  "${compose[@]}" up -d --wait postgres >/dev/null 2>&1 || return 1
  printf 'ALTER ROLE "%s" PASSWORD '\''%s'\'';\n' "$postgres_user" "$password" |
    "${compose[@]}" exec -T -u postgres postgres \
      psql -v ON_ERROR_STOP=1 -U "$postgres_user" -d "$postgres_db" >/dev/null 2>&1
}

recover_running_secrets() {
  local secret_dir="$TARGET_DIR/secrets"
  local names=(
    postgres_password.txt
    settings_key.txt
    token_key.txt
    playback_key.txt
    bootstrap_token.txt
  )
  local containers container name secret_name path temporary found missing

  if [[ -L "$secret_dir" || ( -e "$secret_dir" && ! -d "$secret_dir" ) ]]; then
    fail "install_dir_unsafe" "Installation secrets path is unsafe"
  fi
  mkdir -p -- "$secret_dir"
  chmod 700 "$secret_dir"
  command -v docker >/dev/null 2>&1 || return 0
  if ! containers="$(docker ps --filter 'label=com.docker.compose.project=sakuraplayer' --format '{{.ID}}' 2>/dev/null)"; then
    return 0
  fi
  [[ -n "$containers" ]] || return 0

  missing=()
  for name in "${names[@]}"; do
    path="$secret_dir/$name"
    if [[ -L "$path" || ( -e "$path" && ! -f "$path" ) ]]; then
      fail "install_dir_unsafe" "Installation secret path is unsafe"
    fi
    [[ -f "$path" ]] && continue

    secret_name="${name%.txt}"
    found=0
    for container in $containers; do
      temporary="$(mktemp "$secret_dir/.${name}.recover.XXXXXX")"
      if docker cp "$container:/run/secrets/$secret_name" "$temporary" >/dev/null 2>&1 &&
        [[ -f "$temporary" && ! -L "$temporary" ]]; then
        chmod 600 "$temporary"
        if ln "$temporary" "$path" 2>/dev/null; then
          rm -f -- "$temporary"
          found=1
          break
        fi
      fi
      rm -f -- "$temporary"
    done
    [[ "$found" == 1 ]] || missing+=("$name")
  done

  if [[ ${#missing[@]} -gt 0 ]]; then
    fail "existing_secret_unavailable" "Could not recover all secrets from the existing SakuraPlayer containers"
  fi
}

main() {
  require_command curl
  require_command mktemp
  require_command tar
  require_command rm
  require_command cp
  require_command chmod
  require_command ln
  require_command mv
  require_command find
  require_command grep

  resolve_target_dir
  select_network_config
  CURRENT_TEMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/sakuraplayer-install.XXXXXX")"
  local tag
  tag="$(resolve_latest_tag)"
  download_and_run "$tag" "$@"
}

main "$@"
