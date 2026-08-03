# SakuraPlayer Backend

The backend is a private Docker deployment for one administrator. Compose publishes the API on `127.0.0.1:8000` by default and never publishes PostgreSQL to the host.

Remote clients must connect through HTTPS or a trusted encrypted VPN. This repository does not provide a public internet deployment guide, automatic certificate issuance, or a plaintext public endpoint.

## One-command Linux install

Official Linux release bundles contain this Compose file, `.env.example`, a fixed `.release-version`, and `install.sh`. After verifying and extracting the release archive, run:

```bash
./install.sh
```

The installer requires Docker Engine, Docker Compose v2, OpenSSL, and `flock`. It creates a release `.env`, generates the five independent secret files with private permissions, pulls the fixed SemVer image, validates Compose, and waits for every service to become healthy. It never prints secret values. Re-running it preserves every valid existing secret and `.env`; unsafe paths, malformed values, reused material, and concurrent runs fail before Compose starts.

From a source checkout, run `bash backend/install.sh`; the installer derives the image version from `windows/pubspec.yaml`. Manual deployments may still create the files referenced by `.env.example`, but must preserve the same format, permission, uniqueness, and loopback rules.

The one-shot `migrate` service performs the explicit Alembic upgrade; API, worker, and scheduler only check the Schema head and never migrate it. The long-running processes start only after migration succeeds.

The four named volumes keep PostgreSQL data, permanent catalog images, provider manifests, and necessary redacted logs separate. v1 does not create an automatic backup for the database or images. Operators must arrange any desired backup outside SakuraPlayer.

Windows delivery uses a private installer. HarmonyOS delivery remains blocked until the Windows and real 115 gates pass, then uses developer-signed sideloading. No public app-store workflow is included.

## Development verification

Backend implementation uses Focused/Fast checks for short feedback and a Final gate before a task is completed or committed. Fast results never replace the full PostgreSQL and Compose evidence required by Final. The authoritative commands, current script capabilities, and cache safety rules are in [tests/README.md](tests/README.md); the repository-wide sequence is in [implementation-workflow.md](../docs/specs/001-sakuraplayer-v1/implementation-workflow.md).

See `../LICENSE` and `../THIRD_PARTY_NOTICES.md` before redistributing builds or imported source.
