# Backend Test Entry Points

The repository uses three verification levels. Focused and Fast shorten feedback; only Final is completion evidence for a backend task.

| Level | Purpose | Current entry point |
|---|---|---|
| Focused | One behavior or implementation batch | Reused test image with the current repository mounted read-only |
| Fast | Broad self-contained regression and host configuration assertions | Reused test image plus host checks |
| Final | Full isolated PostgreSQL, Phase 1 E2E, and five-service operational evidence | `backend/tests/run-compose.ps1` |

## Focused

Build the Python 3.10.16 test image when `pyproject.toml`, the Dockerfile, the base image, or a locked dependency changes:

```powershell
docker build -f backend/docker/api.Dockerfile --target test -t sakuraplayer-test .
```

For source-only changes, reuse that image and mount the current repository read-only. Replace the test path with the smallest affected set:

```powershell
$repoRoot = (Resolve-Path .).Path
docker run --rm `
  --mount "type=bind,source=$repoRoot,target=/workspace,readonly" `
  --workdir /workspace/backend `
  --entrypoint python `
  sakuraplayer-test `
  -m pytest tests/unit/shared/test_redaction.py -q -p no:cacheprovider
```

The mount is the source of truth. Do not use an old image without the mount for source-only verification, because it may execute the image's stale copy of `src`, tests, migrations, or documentation.

## Fast

Run the broad self-contained suite from the same mounted image:

```powershell
$repoRoot = (Resolve-Path .).Path
docker run --rm `
  --mount "type=bind,source=$repoRoot,target=/workspace,readonly" `
  --workdir /workspace/backend `
  --entrypoint python `
  sakuraplayer-test `
  -m pytest tests/start tests/unit tests/integration/api tests/integration/events `
  tests/integration/identity/test_auth_api.py `
  -m "not integration and not host_docker" -q -p no:cacheprovider
```

Run host Docker configuration assertions with any supported local Python; no third-party Python package is required:

```powershell
python backend/tests/start/test_docker_entrypoint.py
```

Fast fails immediately on any failing check. A green Fast run allows final read-only audits to begin, but it does not satisfy a task Definition of Done and must not be recorded as Final.

### Focused PostgreSQL

PostgreSQL integration tests may reuse a dedicated test PostgreSQL process, never a development or production database. Reuse applies only to the server process: every test run must create a unique database and drop it in `finally`. Cleanup after an interrupted run must target only databases carrying that run ID.

The repository does not yet provide a dedicated reusable PostgreSQL runner or a `-Gate Fast` parameter. Until those are implemented, use the Final workflow for complete PostgreSQL evidence and do not document manual ad hoc database commands as a supported gate.

## Final

Run the complete isolated Compose, PostgreSQL, restart, and readiness workflow only after implementation, Fast, the complete diff review, and read-only audits have converged:

```powershell
pwsh -NoProfile -File backend/tests/run-compose.ps1
```

`run-compose.ps1` currently has no parameters and is the Final entry point. It builds the test and application images, runs all required self-contained and PostgreSQL integration tests, starts API/worker/scheduler/PostgreSQL with migration, performs the authentication canary and secret log scan, verifies restart persistence and ready degradation/recovery, then removes temporary containers, networks, volumes, images, and secret files in `finally`.

`tests/e2e` is collected together with `tests/integration` in that single PostgreSQL step. The E2E suite uses a unique migrated database per test and production service composition with deterministic external adapters. Real API/worker/scheduler process health, restart persistence, and readiness degradation remain owned by the surrounding Compose workflow, so E2E does not launch a second process tree or a second Compose run.

Run complete Compose at most once per Final attempt. If it fails, leave Final, fix the cause, rerun affected Fast checks and audits, and start a new Final attempt. Any later change to production code, tests, migrations, configuration, Dockerfiles, or verification scripts invalidates the previous Final result.

Final does not access real 115, JavDB writes, or paid AI. Those remain explicit gates in their designated E2E tasks.

## Planned runner optimization

When the test infrastructure is changed, it must preserve these contracts:

- Add explicit Fast and Final modes while keeping no-argument behavior compatible with Final until all callers migrate.
- Separate dependency installation from source copy, use BuildKit/pip cache without secrets, and run current sources through a read-only repository mount.
- Reuse a dedicated test PostgreSQL service for Fast while keeping unique per-run databases.
- Keep Final isolated and retain its migration, health, canary, secret scan, restart, degradation/recovery, and temporary-resource cleanup coverage.
- Allow shared dependency images and secret-free build caches to survive Final; provide a separate explicit cache purge command instead of deleting them on every task.
