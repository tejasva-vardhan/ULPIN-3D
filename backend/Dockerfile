FROM python:3.12-slim
WORKDIR /code
RUN apt-get update && apt-get install -y --no-install-recommends libexpat1 postgresql-client \
    && rm -rf /var/lib/apt/lists/*
# Railway build context = repo root, so paths are relative to repo root
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY backend/sql ./sql
COPY backend/start.sh /start.sh
RUN chmod +x /start.sh
COPY data /code/data
ENV PYTHONUNBUFFERED=1
ENV PORT=8000
EXPOSE 8000
CMD ["/start.sh"]
