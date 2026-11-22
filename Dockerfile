# syntax=docker/dockerfile:1

# ---- frontend build ---------------------------------------------------------------------
FROM node:22-bookworm-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- python deps ------------------------------------------------------------------------
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS build
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project
COPY README.md ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-editable

# ---- runtime ----------------------------------------------------------------------------
FROM python:3.12-slim-bookworm
RUN useradd --uid 1000 --create-home --shell /usr/sbin/nologin pulse
COPY --from=build --chown=pulse:pulse /app/.venv /app/.venv
COPY --from=web --chown=pulse:pulse /web/dist /app/static
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PULSE_DATA_DIR=/data \
    PULSE_FIXTURES_DIR=/fixtures \
    PULSE_STATIC_DIR=/app/static
WORKDIR /app
USER pulse
EXPOSE 8000
ENTRYPOINT ["pulse"]
CMD ["serve"]
