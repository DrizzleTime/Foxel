FROM docker.io/oven/bun:1.2-slim AS frontend-builder

WORKDIR /app/web

COPY web/package.json web/bun.lock ./
RUN bun install --frozen-lockfile

COPY web/ ./

RUN bun run build

FROM docker.io/library/python:3.14-slim AS python-builder

WORKDIR /build

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv==0.13.1
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project --no-cache

RUN curl -fL --retry 3 https://github.com/DrizzleTime/FoxelUpgrade/archive/refs/heads/main.tar.gz -o /tmp/migrate.tgz \
    && mkdir -p /build/migrate \
    && tar -xzf /tmp/migrate.tgz --strip-components=1 -C /build/migrate \
    && rm -rf /tmp/migrate.tgz

FROM docker.io/library/python:3.14-slim AS runtime

WORKDIR /app

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/* /var/log/apt /var/cache/apt/archives

COPY --from=python-builder /opt/venv /opt/venv
COPY --from=python-builder /build/migrate /app/migrate

RUN /opt/venv/bin/python -c "from tortoise import Tortoise, exceptions; import gunicorn; from uvicorn.workers import UvicornWorker"

COPY . .

COPY --from=frontend-builder /app/web/dist /app/web/dist

RUN mkdir -p data/db data/mount && \
    chmod 777 data/db data/mount && \
    chmod +x setup/foxel_cli.py && \
    ln -sf /app/setup/foxel_cli.py /usr/local/bin/foxel
    
EXPOSE 80

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

CMD ["/entrypoint.sh"]
