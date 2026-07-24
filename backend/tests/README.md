# TASK-001 Test Entry Points

Run the self-contained Python 3.10.16 suite through the test image:

```powershell
docker build -f backend/docker/api.Dockerfile --target test -t sakuraplayer-task001-test .
docker run --rm --entrypoint python sakuraplayer-task001-test -m pytest tests/start -m "not host_docker" -q
```

Run host Docker configuration assertions with any supported local Python; no third-party Python package is required:

```powershell
python backend/tests/start/test_docker_entrypoint.py
```

Run the complete isolated Compose, PostgreSQL, restart, and readiness workflow:

```powershell
pwsh -NoProfile -File backend/tests/run-compose.ps1
```

The workflow creates random test-only secret files under the system temporary directory and removes its containers, network, volumes, images, and secret files in `finally`. It does not access real 115, JavDB writes, or paid AI.
