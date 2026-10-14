# One public web service: build React and serve it with the Python API.
FROM node:22-alpine AS frontend-build
WORKDIR /frontend
RUN npm install -g pnpm@11.19.0
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm run build

FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    JSSP_DB_PATH=/app/storage/instances.sqlite3

COPY backend/requirements.lock backend/requirements.lock
RUN pip install --no-cache-dir -r backend/requirements.lock
COPY backend/ backend/
COPY data/ data/
COPY --from=frontend-build /frontend/dist/ frontend/dist/

RUN useradd --create-home appuser \
    && mkdir -p /app/storage \
    && chown appuser:appuser /app/storage
USER appuser
EXPOSE 10000
# Render specifies PORT; fallback makes local Docker testing straightforward.
CMD ["sh", "-c", "exec uvicorn backend.cloud:app --host 0.0.0.0 --port ${PORT:-10000}"]
