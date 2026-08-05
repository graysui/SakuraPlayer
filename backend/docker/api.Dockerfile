FROM python:3.10.16-slim@sha256:f9fd9a142c9e3bc54d906053b756eb7e7e386ee1cf784d82c251cf640c502512 AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/workspace/backend/src

WORKDIR /workspace/backend

COPY backend/pyproject.toml ./
COPY backend/src ./src
COPY backend/alembic.ini ./
COPY backend/alembic ./alembic
COPY backend/docker/entrypoint.sh ./docker/entrypoint.sh
COPY backend/README.md ./README.md
COPY LICENSE /workspace/LICENSE
COPY THIRD_PARTY_NOTICES.md /workspace/THIRD_PARTY_NOTICES.md

RUN python -m pip install --no-cache-dir --disable-pip-version-check . \
    && chmod 0755 /workspace/backend/docker/entrypoint.sh

ENTRYPOINT ["/workspace/backend/docker/entrypoint.sh"]

FROM base AS test
COPY backend/tests ./tests
COPY backend/install.sh ./install.sh
COPY backend/install-latest.sh ./install-latest.sh
COPY backend/.env.example ./.env.example
COPY backend/README.docker.md ./README.docker.md
COPY backend/docker/api.Dockerfile ./docker/api.Dockerfile
COPY backend/docker-compose.yml ./docker-compose.yml
COPY docs /workspace/docs
COPY .github /workspace/.github
COPY tools /workspace/tools
COPY windows/pubspec.yaml /workspace/windows/pubspec.yaml
COPY windows/tool/build_windows_installer.ps1 /workspace/windows/tool/build_windows_installer.ps1
COPY windows/tool/package/SakuraPlayer.iss /workspace/windows/tool/package/SakuraPlayer.iss
RUN python -m pip install --no-cache-dir --disable-pip-version-check ".[test]"
CMD ["python", "-m", "pytest", "tests/start", "tests/unit", "tests/integration/identity/test_auth_api.py", "-m", "not integration and not host_docker"]

FROM base AS runtime
CMD ["python", "-m", "sakuraplayer.api"]
