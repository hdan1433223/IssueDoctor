FROM node:22-alpine AS frontend
WORKDIR /build
COPY package.json package-lock.json postcss.config.js tailwind.config.js ./
RUN npm ci
COPY issuedoctor/templates ./issuedoctor/templates
COPY issuedoctor/static ./issuedoctor/static
RUN npm run build

FROM python:3.12-slim

# 默认构建只安装核心依赖，镜像内不含 PyTorch / Chromium（体积从 GB 级降到百 MB 级）。
# 需要可选能力时通过构建参数启用：
#   docker build --build-arg WITH_VECTOR=1 --build-arg WITH_PDF=1 .
ARG WITH_VECTOR=0
ARG WITH_PDF=0

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ISSUEDOCTOR_DOCKER=1 \
    ISSUEDOCTOR_DATA_DIR=/data
WORKDIR /app

COPY requirements.txt requirements-vector.txt requirements-pdf.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt

# 可选能力：本地语义向量（会连带安装 PyTorch CPU 版）
RUN if [ "$WITH_VECTOR" = "1" ]; then \
        python -m pip install --no-cache-dir \
            --extra-index-url https://download.pytorch.org/whl/cpu \
            -r requirements-vector.txt ; \
    fi

# 可选能力：服务端 PDF 导出（Playwright + Chromium）
COPY docker/apt-retries.conf /etc/apt/apt.conf.d/80-issuedoctor-retries
COPY docker/debian.sources /etc/apt/sources.list.d/debian.sources
RUN if [ "$WITH_PDF" = "1" ]; then \
        python -m pip install --no-cache-dir -r requirements-pdf.txt && \
        PLAYWRIGHT_BROWSERS_PATH=/ms-playwright python -m playwright install --with-deps chromium ; \
    fi
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

COPY . .
COPY --from=frontend /build/issuedoctor/static ./issuedoctor/static
RUN useradd --create-home --uid 10001 issuedoctor \
    && mkdir -p /data \
    && chown -R issuedoctor:issuedoctor /app /data
USER issuedoctor
EXPOSE 5000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/healthz', timeout=3)"
CMD ["sh", "-c", "python -m flask --app wsgi db upgrade && gunicorn --bind 0.0.0.0:5000 --workers 1 --threads 4 --timeout 180 wsgi:app"]
