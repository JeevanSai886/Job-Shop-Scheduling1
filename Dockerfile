
FROM node:22-alpine AS frontend-build

WORKDIR /project
RUN apk add --no-cache unzip
RUN npm install -g pnpm@11.19.0

COPY Job-Shop-Scheduling-Render-Ready.zip /tmp/project.zip
RUN unzip -q /tmp/project.zip -d /project

WORKDIR /project/Job-Shop-Scheduling/frontend
RUN pnpm install --frozen-lockfile
RUN pnpm run build

FROM python:3.12-slim
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    JSSP_DB_PATH=/app/storage/instances.sqlite3

COPY --from=frontend-build /project/Job-Shop-Scheduling/backend/requirements.lock /app/backend/requirements.lock

RUN pip install --no-cache-dir -r /app/backend/requirements.lock

COPY --from=frontend-build /project/Job-Shop-Scheduling/backend/ /app/backend/
COPY --from=frontend-build /project/Job-Shop-Scheduling/data/ /app/data/
COPY --from=frontend-build /project/Job-Shop-Scheduling/frontend/dist/ /app/frontend/dist/

RUN useradd --create-home appuser \
    && mkdir -p /app/storage \
    && chown appuser:appuser /app/storage

USER appuser

EXPOSE 10000

CMD ["sh", "-c", "exec uvicorn backend.cloud:app --host 0.0.0.0 --port ${PORT:-10000}"]
