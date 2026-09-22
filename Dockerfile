# Packages the backend AND the website into one container, for deployment.
FROM python:3.12-slim

WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend backend
COPY frontend frontend

WORKDIR /app/backend
ENV PYTHONUNBUFFERED=1
# Hosting services tell the app which port to use through $PORT (default 8000).
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
