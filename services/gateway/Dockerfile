# 生产镜像（构建上下文 = 仓库根目录）
FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements-prod.txt /app/requirements-prod.txt
RUN pip install -r requirements-prod.txt

COPY packages/contract-sdk /app/packages/contract-sdk
COPY packages/kernel /app/packages/kernel
COPY services/gateway /app/services/gateway
RUN pip install --no-deps \
        /app/packages/contract-sdk \
        /app/packages/kernel \
        /app/services/gateway

RUN useradd --create-home --shell /usr/sbin/nologin appuser \
 && chown -R appuser:appuser /app
USER appuser

WORKDIR /app/services/gateway
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=3)"

CMD ["uvicorn", "gateway_app.main:app", "--host", "0.0.0.0", "--port", "8000"]