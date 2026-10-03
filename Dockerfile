FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:0.8.17 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    HARBINGER_CONFIG=/app/config.yaml \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies first so they cache independently of the source.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY harbinger ./harbinger
COPY web ./web
COPY schema ./schema
RUN uv sync --frozen --no-dev

RUN useradd --create-home --uid 1000 harbinger \
    && mkdir -p /app/var \
    && chown -R harbinger:harbinger /app/var
USER harbinger

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=4).status == 200 else 1)"]

CMD ["/app/.venv/bin/harbinger", "serve"]
