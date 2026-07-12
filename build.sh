#!/usr/bin/env bash
set -o errexit

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -c "from catalog.background_removal import preload_model; preload_model()"
python manage.py collectstatic --noinput
python manage.py migrate --noinput
