FROM python:3.10.16-slim AS base

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
COPY backend/docker/api.Dockerfile ./docker/api.Dockerfile
RUN python -m pip install --no-cache-dir --disable-pip-version-check ".[test]"
CMD ["python", "-m", "pytest", "tests/start", "tests/unit", "tests/integration/identity/test_auth_api.py", "-m", "not integration and not host_docker"]

FROM base AS runtime
CMD ["python", "-m", "sakuraplayer.api"]
