FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN groupadd --system guardian \
    && useradd --system --gid guardian --create-home guardian \
    && mkdir -p /var/lib/guardian/pki /var/lib/guardian/pki-root \
    && chown -R guardian:guardian /var/lib/guardian

WORKDIR /app

COPY pyproject.toml alembic.ini ./
COPY app ./app
COPY migrations ./migrations
COPY README.md ./README.md

RUN python -m pip install --upgrade pip \
    && python -m pip install .

USER guardian
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=3)" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
