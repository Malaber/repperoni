ARG PYTHON_IMAGE=python:3.14-slim@sha256:cea0e6040540fb2b965b6e7fb5ffa00871e632eef63719f0ea54bca189ce14a6
FROM ${PYTHON_IMAGE} AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    AUTO_MIGRATE=false \
    ENVIRONMENT=production \
    DATABASE_URL=sqlite+aiosqlite:////data/repperoni.db
WORKDIR /app

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid 10001 --no-create-home --home-dir /app \
        --shell /usr/sbin/nologin app \
    && mkdir -p /data \
    && chown 10001:10001 /data \
    && chmod 0700 /data

COPY requirements.lock ./
RUN python -m pip install --no-cache-dir --require-hashes -r requirements.lock

COPY pyproject.toml README.md ./
COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic
RUN python -m pip install --no-cache-dir --no-deps --no-build-isolation .

COPY docker/start.sh ./docker/start.sh
RUN chown -R app:app /app
USER 10001:10001
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=5 \
  CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/health')"

FROM base AS test
USER root
COPY requirements-dev.lock ./
COPY requirements-bootstrap.lock ./
COPY tests ./tests
COPY tasks.py ./tasks.py
COPY Dockerfile docker-compose.yml ./
COPY .dockerignore ./
COPY .github ./.github
COPY deploy ./deploy
COPY scripts ./scripts
RUN python -m pip install --no-cache-dir --require-hashes -r requirements-dev.lock \
    && python -m pip install --no-cache-dir --no-deps --no-build-isolation -e .
USER 10001:10001
RUN python -m pytest

FROM base AS production
ARG REPPERONI_VERSION=0.0.0
ARG REPPERONI_REVISION=unknown
ENV APP_VERSION=${REPPERONI_VERSION} \
    APP_REVISION=${REPPERONI_REVISION}
LABEL org.opencontainers.image.title="Repperoni" \
      org.opencontainers.image.source="https://github.com/Malaber/repperoni" \
      org.opencontainers.image.version="${REPPERONI_VERSION}" \
      org.opencontainers.image.revision="${REPPERONI_REVISION}"
CMD ["sh", "docker/start.sh"]
