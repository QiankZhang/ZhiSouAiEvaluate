# 智搜效果评估平台 —— 单容器镜像（后端 FastAPI + 前端静态资源）
# 构建上下文必须是【仓库根】：
#   docker build -t zhisou:latest -f site/deploy/Dockerfile .
# 说明：config.py 按 backend/../.. 定位仓库根，因此镜像内代码放在 /app 下，
#       保持 /app/site 与 /app/skills 同级。
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# 先装依赖，利用镜像层缓存（requirements 不变则跳过重装）
COPY site/requirements.txt /app/site/requirements.txt
RUN pip install -r /app/site/requirements.txt

# 应用代码 + 内置技能 + 已构建前端（site/frontend/dist 由 deploy 分支带入）
COPY site /app/site
COPY skills /app/skills

WORKDIR /app/site
EXPOSE 8000

# 单进程：SQLite 持久化是「整份内存状态定时快照」，多 worker 会互相覆盖，禁止加 --workers
CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
