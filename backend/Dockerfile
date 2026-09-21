FROM python:3.12-slim
WORKDIR /code
RUN apt-get update && apt-get install -y --no-install-recommends libexpat1 postgresql-client \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY ../data /code/data
ENV PYTHONUNBUFFERED=1
# Railway sets PORT dynamically; fallback to 8000 for local Docker
CMD sh -c "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"
