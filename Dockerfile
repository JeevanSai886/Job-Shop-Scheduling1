FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt backend/requirements.lock ./backend/
RUN pip install --no-cache-dir -r backend/requirements.lock
COPY backend ./backend
COPY data ./data
RUN useradd --create-home appuser && mkdir /app/storage && chown appuser:appuser /app/storage
ENV JSSP_DB_PATH=/app/storage/instances.sqlite3
USER appuser
EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
