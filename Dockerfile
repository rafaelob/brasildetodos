FROM node:24-bookworm-slim AS web
WORKDIR /app/web
COPY web/package*.json ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi
COPY web/ ./
RUN npm run build

FROM python:3.13-slim-bookworm AS application
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 BDT_STATIC_DIR=/app/web/dist BDT_DATA_DIR=/app/data
COPY pyproject.toml README.md LICENSE ./
COPY backend/ backend/
RUN pip install --no-cache-dir '.[postgres]' && useradd --uid 10001 --create-home app && mkdir -p /app/data && chown app:app /app/data
COPY --from=web /app/web/dist web/dist
ARG REVISION=development
ENV BDT_REVISION=${REVISION}
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=3)"
CMD ["uvicorn","bdt.api:create_app","--factory","--host","0.0.0.0","--port","8000","--no-proxy-headers"]
