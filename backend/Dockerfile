FROM python:3.12-slim
WORKDIR /code
RUN apt-get update && apt-get install -y --no-install-recommends libexpat1 postgresql-client \
    && rm -rf /var/lib/apt/lists/*
# Railway build context = repo root, so paths are relative to repo root
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY backend/sql ./sql
COPY data /code/data
ENV PYTHONUNBUFFERED=1
# Startup script: run init.sql first (idempotent), then start the API
RUN printf '#!/bin/sh\n\
# Convert SQLAlchemy URL format to standard psql format\n\
PSQL_URL=$(echo "$DATABASE_URL" | sed "s|postgresql+psycopg://|postgresql://|")\n\
echo "Running init.sql on database..."\n\
psql "$PSQL_URL" -f /code/sql/init.sql\n\
echo "Starting API server..."\n\
exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}\n\
' > /start.sh && chmod +x /start.sh
CMD ["/start.sh"]
