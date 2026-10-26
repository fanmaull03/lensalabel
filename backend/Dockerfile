FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    EASYOCR_GPU=0 \
    EASYOCR_MODULE_PATH=/opt/easyocr

WORKDIR /app/backend
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-deploy.txt ./
RUN python -m pip install --no-cache-dir torch==2.13.0 torchvision==0.28.0 \
        --index-url https://download.pytorch.org/whl/cpu \
    && python -m pip install --no-cache-dir -r requirements-deploy.txt

COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY deploy/ ./deploy/
RUN python -c "import easyocr; easyocr.Reader(['id', 'en'], gpu=False)" \
    && useradd --system --uid 10001 --home-dir /app/backend appuser

USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=120s --start-period=180s --retries=2 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=110).close()"
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
