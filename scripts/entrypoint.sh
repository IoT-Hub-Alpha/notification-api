#!/bin/sh
set -e

until pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME"; do
  echo "Waiting for database..."
  sleep 2
done

python manage.py migrate
python manage.py runserver 0.0.0.0:8015