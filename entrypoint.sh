#!/bin/sh
set -e

python manage.py migrate --noinput
python manage.py collectstatic --noinput

# À ajouter :
python manage.py createsuperuser --noinput || true

exec "$@"
