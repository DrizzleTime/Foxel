#!/bin/bash
set -e
python migrate/run.py
nginx -g 'daemon off;' &
exec gunicorn -k uvicorn.workers.UvicornWorker -w 1 -b 0.0.0.0:8000 main:app