#!/bin/bash
set -e
python migrate/run.py
exec gunicorn -k uvicorn.workers.UvicornWorker -w 1 -b 0.0.0.0:80 main:app
