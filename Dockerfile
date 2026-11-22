# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS build
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project
COPY README.md ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim-bookworm
RUN useradd --uid 1000 --create-home --shell /usr/sbin/nologin pulse
COPY --from=build --chown=pulse:pulse /app/.venv /app/.venv
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PULSE_DATA_DIR=/data \
    PULSE_FIXTURES_DIR=/fixtures
WORKDIR /app
USER pulse
EXPOSE 8000
ENTRYPOINT ["pulse"]
CMD ["serve"]
