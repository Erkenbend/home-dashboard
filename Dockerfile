FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies first for better layer caching
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

# UI language (src/home_dashboard/locales/<LANGUAGE>.toml): only that catalog is shipped, an
# unknown one fails the build (see ADR 0006)
ARG LANGUAGE=de

COPY src ./src
RUN test -f "src/home_dashboard/locales/${LANGUAGE}.toml" \
    && find src/home_dashboard/locales -name '*.toml' ! -name "${LANGUAGE}.toml" -delete
RUN uv sync --locked --no-dev

ENV PATH="/app/.venv/bin:$PATH" \
    HOME_DASHBOARD_CONFIG=/config/config.yaml \
    HOME_DASHBOARD_LANGUAGE=${LANGUAGE}

EXPOSE 3274
HEALTHCHECK --interval=60s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:3274/healthz', timeout=4)"

CMD ["home-dashboard", "serve"]
