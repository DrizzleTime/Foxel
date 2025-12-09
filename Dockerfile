FROM oven/bun:1.2-slim AS frontend-builder

WORKDIR /app/web

COPY web/package.json web/bun.lock ./
RUN bun install --frozen-lockfile

COPY web/ ./

RUN bun run build

FROM python:3.13-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip install uv
COPY pyproject.toml uv.lock ./
RUN uv pip install --system . gunicorn \
    && rm -rf /root/.cache

RUN curl -L https://github.com/DrizzleTime/FoxelUpgrade/archive/refs/heads/main.tar.gz -o /tmp/migrate.tgz \
    && mkdir -p /app/migrate \
    && tar -xzf /tmp/migrate.tgz --strip-components=1 -C /app/migrate \
    && rm -rf /tmp/migrate.tgz

COPY --from=frontend-builder /app/web/dist /app/web/dist

COPY . .

RUN mkdir -p data/db data/mount && \
    chmod 777 data/db data/mount && \
    rm -rf /var/log/apt /var/cache/apt/archives
    
EXPOSE 80

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

CMD ["/entrypoint.sh"]
