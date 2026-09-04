# 智搜效果评估平台 —— 单容器镜像（后端 FastAPI + 前端静态资源）
# 构建上下文必须是【仓库根】：
#   docker build -t zhisou:latest -f site/deploy/Dockerfile .
# 说明：config.py 按 backend/../.. 定位仓库根，因此镜像内代码放在 /app 下，
#       保持 /app/site 与 /app/skills 同级。
#
# 基础镜像可配置：
#  - 目标机拉不到 Docker Hub 时用镜像源（docker-run.sh 默认 docker.m.daocloud.io）
#  - 必须用 bullseye(Debian 11/glibc 2.31)：CentOS 7 的老 Docker seccomp 不放行
#    bookworm(glibc 2.36) 的 clone3，容器内起线程会 "can't start new thread"
ARG BASE_IMAGE=python:3.11-slim-bullseye
FROM ${BASE_IMAGE}

# pip 源可配置（内网环境按需传 --build-arg PIP_INDEX_URL=...）
ARG PIP_INDEX_URL=""

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# 主依赖：这一层与历史构建字节一致，命中已有镜像层缓存（目标机常拉不到 PyPI）
COPY site/requirements.txt /app/site/requirements.txt
RUN pip install ${PIP_INDEX_URL:+--index-url $PIP_INDEX_URL} -r /app/site/requirements.txt

# 博文数据集依赖（aiohttp/redis/pandas/tqdm/requests）：全部走仓库内离线 wheels，
# 不碰外网——目标机 PyPI 不可达也能构建。wheels 是 linux cp311 manylinux 轮子。
COPY site/deploy/requirements-weibo.txt /app/site/deploy/requirements-weibo.txt
COPY site/deploy/vendor/wheels-weibo /app/wheels-weibo
RUN pip install --no-index --find-links=/app/wheels-weibo -r /app/site/deploy/requirements-weibo.txt

# 应用代码 + 内置技能 + 已构建前端（site/frontend/dist 由 deploy 分支带入）
COPY site /app/site
COPY skills /app/skills
# 博文数据集：qinglong 流水线随镜像发布，后端子进程调用（见 backend/weibo.py）。
# 依赖新浪内网可达（hbase / redis / 内容接口）——目标机内网满足。
COPY qinglong /app/qinglong
ENV WEIBO_QINGLONG_DIR=/app/qinglong \
    WEIBO_QINGLONG_PYTHON=python3

WORKDIR /app/site
EXPOSE 8000

# 单进程：SQLite 持久化是「整份内存状态定时快照」，多 worker 会互相覆盖，禁止加 --workers
CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
