#!/bin/bash
set -e
python migrate/run.py
port="${FOXEL_PORT:-80}"
exec gunicorn -k uvicorn.workers.UvicornWorker -w 1 -b "0.0.0.0:${port}" main:app
