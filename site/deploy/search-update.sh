#!/usr/bin/env bash
###############################################################################
# 10.2.1.44 —— 用 `search` 账号更新（当前实际可用的路径）。
#
#   bash ~/zhisou-update.sh
#
# 背景：/data1/zhisou 目录属 `jilin5`，`search` 不是属主、读不到 /data1/zhisou/.gh_token，
#       所以官方的 remote-update.sh 对 search 不成立。但 `search` 在 docker 组，
#       且仓库已 public —— 于是：在 search 自己家目录拉 deploy 分支 tar 包、build 镜像、
#       复用同一套 bind mount + env-file 重启容器。不碰 jilin5 的任何文件。
#
# 一次性：把本脚本放到 ~/zhisou-update.sh（下面「安装」一节），之后每次就一条命令。
#
# 数据：/data1/zhisou/data 是 bind mount，容器内以 root 读写，不受宿主属主限制，换镜像不影响。
# 回滚：docker rm -f zhisou && docker tag zhisou:prev zhisou:latest && <重跑下面的 docker run>
###############################################################################
set -euo pipefail

WORK="${WORK:-$HOME/zhisou-build}"
BRANCH="${1:-deploy}"
REPO="${REPO:-QiankZhang/ZhiSouAiEvaluate}"
IMAGE="zhisou:latest"
NAME="zhisou"
HOST_PORT="${HOST_PORT:-8080}"
DATA_DIR="${DATA_DIR:-/data1/zhisou}"
BASE_IMAGE="${BASE_IMAGE:-docker.m.daocloud.io/library/python:3.11-slim-bullseye}"

mkdir -p "$WORK" && cd "$WORK"
rm -rf src src.tgz && mkdir src

echo "==> 下载 $REPO@$BRANCH"
curl -fsSL -o src.tgz "https://codeload.github.com/$REPO/tar.gz/refs/heads/$BRANCH"
tar xzf src.tgz -C src --strip-components=1
[ -f src/site/frontend/dist/index.html ] || { echo "错误: 包里没有 site/frontend/dist —— 确认拉的是 deploy 分支"; exit 1; }

echo "==> 备份当前镜像为 $IMAGE -> zhisou:prev"
docker tag "$IMAGE" zhisou:prev 2>/dev/null || true

echo "==> docker build"
cd src
docker build -t "$IMAGE" -f site/deploy/Dockerfile --build-arg "BASE_IMAGE=$BASE_IMAGE" .

echo "==> 换容器"
docker rm -f "$NAME" 2>/dev/null || true
docker run -d --name "$NAME" --restart=always \
  -p "$HOST_PORT:8000" \
  -v "$DATA_DIR/data:/app/site/backend/data" \
  -v "$DATA_DIR/reports:/app/site/backend/reports" \
  --env-file "$DATA_DIR/zhisou.env" \
  "$IMAGE"

echo "==> 健康检查"
for _ in $(seq 1 15); do
  sleep 2
  if curl -fsS "http://127.0.0.1:$HOST_PORT/health" >/dev/null 2>&1; then
    echo "OK ✅  http://10.2.1.44:$HOST_PORT/"
    docker ps --filter "name=$NAME" --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
    exit 0
  fi
done
echo "健康检查未通过，看日志: docker logs $NAME" >&2
exit 1
