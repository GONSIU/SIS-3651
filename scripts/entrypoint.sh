#!/usr/bin/env bash
set -e

echo "Esperando a PostgreSQL en ${POSTGRES_HOST}:${POSTGRES_PORT}..."
while ! nc -z "${POSTGRES_HOST}" "${POSTGRES_PORT}"; do
  sleep 0.5
done
echo "PostgreSQL disponible."

python manage.py migrate --noinput
python manage.py collectstatic --noinput --clear || true

exec "$@"
