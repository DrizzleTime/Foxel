FROM oven/bun:1.2-slim AS frontend-builder

WORKDIR /app/web

COPY web/package.json web/bun.lock ./
RUN bun install --frozen-lockfile

COPY web/ ./

RUN bun run build

FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && apt-get install -y nginx git && rm -rf /var/lib/apt/lists/*

RUN pip install uv
COPY pyproject.toml uv.lock ./
RUN uv pip install --system . gunicorn

RUN git clone https://github.com/DrizzleTime/FoxelUpgrade /app/migrate

COPY --from=frontend-builder /app/web/dist /app/web/dist

COPY . .

COPY nginx.conf /etc/nginx/nginx.conf

RUN mkdir -p data/db data/mount && \
    chmod 777 data/db data/mount
    
EXPOSE 80

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

CMD ["/entrypoint.sh"]