#!/bin/sh
set -e

# Convert SQLAlchemy URL format (postgresql+psycopg://) to standard psql format (postgresql://)
PSQL_URL=$(echo "$DATABASE_URL" | sed 's|postgresql+psycopg://|postgresql://|')

echo "=== Running init.sql to bootstrap database schema ==="
psql "$PSQL_URL" -f /code/sql/init.sql && echo "=== init.sql complete ===" || echo "=== init.sql had errors (may be safe to ignore if tables already exist) ==="

echo "=== Starting API server ==="
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
