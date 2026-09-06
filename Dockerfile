FROM node:24.20.0-bookworm-slim AS web
WORKDIR /app/web
RUN node -e "if (process.versions.node !== '24.20.0') process.exit(1)"
COPY web/package.json web/package-lock.json web/.npmrc ./
RUN npm ci
COPY web/ ./
COPY ops/check-node.mjs /app/ops/check-node.mjs
RUN npm run build

FROM python:3.14.7-slim-bookworm AS application
WORKDIR /app
RUN python -c "import sys; assert sys.version_info[:3] == (3,14,7)"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 BDT_STATIC_DIR=/app/web/dist BDT_DATA_DIR=/app/data
COPY pyproject.toml README.md LICENSE ./
COPY backend/ backend/
COPY requirements/ requirements/
COPY ops/install_locked.py ops/python_lock_manifest.py ops/
RUN python ops/install_locked.py && useradd --uid 10001 --create-home app && mkdir -p /app/data && chown app:app /app/data
COPY --from=web /app/web/dist web/dist
ARG REVISION=development
ENV BDT_REVISION=${REVISION}
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=3)"
CMD ["uvicorn","bdt.api:create_app","--factory","--host","0.0.0.0","--port","8000","--no-proxy-headers"]
