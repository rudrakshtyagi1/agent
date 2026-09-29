FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/backend
WORKDIR /app
COPY backend/requirements.lock /app/backend/requirements.lock
RUN pip install --no-cache-dir -r backend/requirements.lock
COPY sdk /app/sdk
RUN pip install --no-cache-dir /app/sdk
COPY backend /app/backend
COPY examples /app/examples
COPY evals /app/evals
COPY scripts /app/scripts
RUN useradd --uid 10001 --create-home agentguard && chown -R agentguard:agentguard /app
USER agentguard
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
