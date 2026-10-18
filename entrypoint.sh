#!/bin/bash
set -e
# Container upgrades may preserve PATH from an image that used system Python.
export PATH="/opt/venv/bin:$PATH"
/opt/venv/bin/python migrate/run.py
port="${FOXEL_PORT:-80}"
exec /opt/venv/bin/python -m gunicorn -k uvicorn.workers.UvicornWorker -w 1 -b "0.0.0.0:${port}" main:app
