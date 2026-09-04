FROM node:22-alpine AS ui-build
WORKDIR /src
COPY apps/web-console/package.json ./package.json
RUN npm install --no-audit --no-fund
COPY apps/web-console/ ./
RUN npm run test && npm run build

FROM python:3.12-slim AS wheel-build
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /src
COPY services/web-console-service/pyproject.toml ./pyproject.toml
COPY services/web-console-service/app ./app
RUN python -m pip wheel --no-cache-dir --wheel-dir /wheels .

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 WEB_CONSOLE_STATIC_DIR=/app/static
RUN groupadd --system guardian && useradd --system --gid guardian --home-dir /nonexistent --shell /usr/sbin/nologin guardian
WORKDIR /app
COPY --from=wheel-build /wheels /wheels
RUN python -m pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels
COPY services/web-console-service/app ./app
COPY --from=ui-build /src/dist ./static
RUN chown -R guardian:guardian /app
USER guardian
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
