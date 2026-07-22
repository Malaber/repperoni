ARG PYTHON_VERSION=3.14
FROM python:${PYTHON_VERSION}-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATABASE_URL=sqlite+aiosqlite:////data/repperoni.db
WORKDIR /app

RUN groupadd --system app && useradd --system --gid app --home /app app \
    && mkdir -p /data && chown app:app /data

COPY pyproject.toml README.md ./
COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic
RUN python -m pip install --no-cache-dir .

COPY docker/start.sh ./docker/start.sh
RUN chown -R app:app /app
USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=5 \
  CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/health')"

FROM base AS test
USER root
COPY tests ./tests
COPY tasks.py ./tasks.py
RUN python -m pip install --no-cache-dir -e '.[dev]'
USER app
RUN python -m pytest

FROM base AS production
ARG REPPERONI_VERSION=0.0.0
LABEL org.opencontainers.image.title="Repperoni" \
      org.opencontainers.image.version="${REPPERONI_VERSION}"
CMD ["sh", "docker/start.sh"]
