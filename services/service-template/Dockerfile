# 生产镜像（构建上下文 = 仓库根目录）
# 特点：非编辑安装（site-packages 正式包）、非 root 运行、内置健康检查
FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# 先装运行时依赖（分层缓存）
COPY requirements-prod.txt /app/requirements-prod.txt
RUN pip install -r requirements-prod.txt

# 再装三个本地包（--no-deps：依赖已由 requirements-prod.txt 提供）
COPY packages/contract-sdk /app/packages/contract-sdk
COPY packages/kernel /app/packages/kernel
COPY services/service-template /app/services/service-template
RUN pip install --no-deps \
        /app/packages/contract-sdk \
        /app/packages/kernel \
        /app/services/service-template

# 非 root 运行（安全基线）
RUN useradd --create-home --shell /usr/sbin/nologin appuser \
 && chown -R appuser:appuser /app
USER appuser

WORKDIR /app/services/service-template
EXPOSE 8100

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8100/health/ready', timeout=3)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100"]