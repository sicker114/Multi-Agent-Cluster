# ==========================================================
# Python MCP AI 服务 Dockerfile
# 提供多智能体推理能力，暴露 MCP SSE(HTTP) 端点 /sse
# ==========================================================
FROM python:3.11-slim
LABEL maintainer="enterprise-agent"
WORKDIR /app

ENV TZ=Asia/Shanghai \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# 系统依赖（部分向量/文档解析库需要编译工具）
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc curl \
    && rm -rf /var/lib/apt/lists/*

# 先装依赖，利用层缓存
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# 复制源码
COPY app ./app
COPY scripts ./scripts

# 运行期数据目录：Chroma 向量库 + Checkpoint
RUN mkdir -p /app/data/chroma /app/data/checkpoints

EXPOSE 8000

# 默认以 SSE(HTTP) 传输启动，供 Java SpringAI MCP Client 远程连接
ENV MCP_TRANSPORT=sse \
    MCP_HTTP_HOST=0.0.0.0 \
    MCP_HTTP_PORT=8000

ENTRYPOINT ["python", "-m", "app.server"]
