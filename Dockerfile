FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 安装 uv
RUN pip install --no-cache-dir uv

# 复制依赖文件
COPY pyproject.toml .
COPY .python-version .
COPY README.md .

# 创建虚拟环境并安装依赖
RUN uv venv && \
    . .venv/bin/activate && \
    uv pip install -e .

# 复制应用代码
COPY app/ ./app/

# 复制静态文件（前端管理界面）
COPY static/ ./static/

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# 启动命令
CMD [".venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
