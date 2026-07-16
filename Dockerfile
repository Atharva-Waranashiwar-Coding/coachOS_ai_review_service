FROM python:3.12-slim AS builder

WORKDIR /build
COPY requirements-prod.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements-prod.txt

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN addgroup --system --gid 10001 coachos \
    && adduser --system --uid 10001 --ingroup coachos --home /app coachos

WORKDIR /app
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels
COPY --chown=coachos:coachos . .
RUN chmod 0555 /app/docker/entrypoint.sh

USER 10001:10001
EXPOSE 8000
ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--log-config", "/app/logging.json"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=3)"]
