# Research engine: FastAPI API + in-process scheduler. Data lives on a mounted disk at /data.
FROM python:3.13-slim

# 1 = include the local FinBERT sentiment model (needs about 2 GB RAM at run time); 0 = word list only
ARG INSTALL_AI=1

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    OALGO_DATA_DIR=/data \
    PORT=8000

# same uv release that wrote uv.lock
RUN pip install --no-cache-dir uv==0.11.32
WORKDIR /app

# dependencies first so code changes do not reinstall them
COPY pyproject.toml uv.lock ./
RUN if [ "$INSTALL_AI" = "1" ]; then uv sync --frozen --no-dev --group ai --no-install-project; \
    else uv sync --frozen --no-dev --no-install-project; fi

COPY app ./app
COPY scripts ./scripts

RUN useradd --create-home --uid 10001 oalgo && mkdir -p /data && chown -R oalgo /data /app
USER oalgo

EXPOSE 8000
CMD ["sh", "-c", "exec /app/.venv/bin/uvicorn app.api.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
