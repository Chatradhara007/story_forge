# Packages the backend AND the website into one container, for deployment.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt

COPY backend backend
COPY frontend frontend

# Don't run as root.
RUN useradd --create-home storyforge && chown -R storyforge /app
USER storyforge
WORKDIR /app/backend

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.getenv(\"PORT\",\"8000\")}/health', timeout=4)"

# ONE worker process: background jobs and the per-book lock live inside it.
# --proxy-headers: behind a host's proxy, see each visitor's real address (used to slow
# down password guessing).
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --proxy-headers --forwarded-allow-ips='*'"]
