# ---- frontend build
# the static frontend is the same for every platform: build it once, natively
FROM --platform=$BUILDPLATFORM node:20-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- python deps
FROM python:3.12-slim-trixie AS py
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/venv
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# ---- wireproxy: user-space WireGuard -> local HTTP proxy, the optional backup route to Telegram
# (pinned release, checked against its published sha256)
FROM python:3.12-slim-trixie AS wireproxy
ARG TARGETARCH=amd64
ARG WIREPROXY=v1.1.3
ADD https://github.com/windtf/wireproxy/releases/download/${WIREPROXY}/wireproxy_linux_${TARGETARCH}.tar.gz /tmp/wp.tgz
RUN case "$TARGETARCH" in \
      amd64) sum=e88c1d090740373fc606c1bafd81d9a5eadc642cce5667616e20e9d7a444f51c ;; \
      arm64) sum=370e00bd2167960d1ecd1c3c1439715bbaa94a0a110a2040468670c9af6021b6 ;; \
      *) echo "no wireproxy for $TARGETARCH" && exit 1 ;; \
    esac \
 && echo "$sum  /tmp/wp.tgz" | sha256sum -c - \
 && tar -xzf /tmp/wp.tgz -C /usr/local/bin wireproxy && chmod 755 /usr/local/bin/wireproxy

# ---- runtime
# trixie ships pg_dump 17, which can back up the PostgreSQL 16 server before migrations
FROM python:3.12-slim-trixie
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --uid 1000 --create-home planner && mkdir /data && chown planner /data
COPY --from=py /venv /venv
COPY --from=wireproxy /usr/local/bin/wireproxy /usr/local/bin/wireproxy
WORKDIR /app
COPY backend/ ./
COPY --from=web /web/dist ./static
ENV PATH=/venv/bin:$PATH PYTHONUNBUFFERED=1 PLANNER_DATA_DIR=/data
USER planner
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health').status==200 else 1)"
CMD ["python", "-m", "app"]
