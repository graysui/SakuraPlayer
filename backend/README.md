# SakuraPlayer Backend

The backend is a private Docker deployment for one administrator. Compose publishes the API on `127.0.0.1:8000` by default and never publishes PostgreSQL to the host.

Remote clients must connect through HTTPS or a trusted encrypted VPN. This repository does not provide a public internet deployment guide, automatic certificate issuance, or a plaintext public endpoint.

## One-command Linux install

The recommended Linux path is a single command. Run it from the directory where SakuraPlayer should keep its `.env` and `secrets/`; it resolves the latest GitHub Release, downloads the matching Docker deployment archive into a temporary directory, copies the deployment files to the current directory, and runs the installer there. It does not require manually downloading a Release, extracting it, or checking SHA-256:

```bash
curl -fsSL https://raw.githubusercontent.com/graysui/SakuraPlayer/main/backend/install-latest.sh | bash
```

On the first interactive run, the script asks for the Docker publish IPv4 address and API port. Press Enter to keep `127.0.0.1` and `8000`; enter the NAS private address, such as `192.168.1.50`, when trusted LAN clients must connect directly. Non-interactive runs use those defaults automatically. If `.env` already exists, its values are preserved and no prompt is shown.

For offline or manually reviewed deployments, download a release archive, optionally verify its `.sha256` file, extract it, and run `./install.sh` from the extracted directory.

The installer requires Docker Engine, Docker Compose v2, OpenSSL, and `flock`. It creates a release `.env`, generates the five independent secret files with private permissions, pulls the fixed SemVer image, validates Compose, and waits for every service to become healthy. It never prints secret values. Re-running it preserves every valid existing secret and `.env`; unsafe paths, malformed values, reused material, and concurrent runs fail before Compose starts.

From a source checkout, run `bash backend/install.sh`; the installer derives the image version from `windows/pubspec.yaml`. Manual deployments may still create the files referenced by `.env.example`, but must preserve the same format, permission, uniqueness, and loopback rules.

The one-shot `migrate` service performs the explicit Alembic upgrade; API, worker, and scheduler only check the Schema head and never migrate it. The long-running processes start only after migration succeeds.

The deployment directory keeps PostgreSQL data, permanent catalog images, provider manifests, and necessary redacted logs in `data/postgres/`, `data/catalog-images/`, `data/provider-cache/`, and `data/app-logs/`. These are bind mounts relative to the installation directory, so the data does not fall back to Docker's system storage. When the remote installer finds a legacy `sakuraplayer_*` named volume, it copies the contents into the matching directory before startup and leaves the original volume untouched. v1 does not create an automatic backup for the database or images. Operators must arrange any desired backup outside SakuraPlayer.

Windows delivery uses a private installer. HarmonyOS delivery remains blocked until the Windows and real 115 gates pass, then uses developer-signed sideloading. No public app-store workflow is included.

## Development verification

Backend implementation uses Focused/Fast checks for short feedback and a Final gate before a task is completed or committed. Fast results never replace the full PostgreSQL and Compose evidence required by Final. The authoritative commands, current script capabilities, and cache safety rules are in [tests/README.md](tests/README.md); the repository-wide sequence is in [implementation-workflow.md](../docs/specs/001-sakuraplayer-v1/implementation-workflow.md).

See `../LICENSE` and `../THIRD_PARTY_NOTICES.md` before redistributing builds or imported source.
