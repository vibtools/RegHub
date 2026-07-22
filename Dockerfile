FROM python:3.13-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build
COPY pyproject.toml README.md ./
COPY app ./app
RUN python -m pip wheel --wheel-dir /wheels .

FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/home/reghub/.local/bin:${PATH}"

RUN addgroup --system reghub && adduser --system --ingroup reghub --home /home/reghub reghub
WORKDIR /app

COPY --from=builder /wheels /wheels
RUN python -m pip install --no-cache-dir --no-index --find-links=/wheels reghub==0.3.2.0 \
    && python -m pip check \
    && python -c "import app; assert 'site-packages' in app.__file__" \
    && rm -rf /wheels

COPY alembic.ini ./
COPY migrations ./migrations
COPY scripts ./scripts
COPY templates ./templates

RUN chmod +x /app/scripts/entrypoint.sh && chown -R reghub:reghub /app
USER reghub

EXPOSE 8000
STOPSIGNAL SIGTERM
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/ready', timeout=3)" || exit 1

ENTRYPOINT ["/app/scripts/entrypoint.sh"]
