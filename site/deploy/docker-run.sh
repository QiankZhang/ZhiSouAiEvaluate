#!/usr/bin/env bash
###############################################################################
# 目标机（CentOS 7 / 无 root / 有 Docker）部署脚本 —— 以 search 用户执行。
# 首次部署和日常更新都跑这一个：重新 build 镜像 + 滚动重启容器。
#
#   bash /data1/zhisou/app/site/deploy/docker-run.sh
#
# 前置：
#   - /data1/zhisou/app  已 git clone（deploy 分支，含 site/frontend/dist）
#   - /data1/zhisou/zhisou.env  已按 zhisou.env.example 创建
#   - 当前用户能执行 docker（在 docker 组）
###############################################################################
set -euo pipefail

APP_DIR="${APP_DIR:-/data1/zhisou}"
SRC="$APP_DIR/app"
IMAGE="${IMAGE:-zhisou:latest}"
NAME="${NAME:-zhisou}"
HOST_PORT="${HOST_PORT:-8080}"
ENV_FILE="$APP_DIR/zhisou.env"

die() { echo "错误: $*" >&2; exit 1; }

[ -f "$SRC/site/frontend/dist/index.html" ] || die "缺前端产物 $SRC/site/frontend/dist —— clone 的必须是 deploy 分支"
[ -f "$ENV_FILE" ] || die "缺 $ENV_FILE —— 复制 $SRC/site/deploy/zhisou.env.example 过去并按需修改"
command -v docker >/dev/null || die "没有 docker 命令"

mkdir -p "$APP_DIR/data" "$APP_DIR/reports"

echo "==> git 版本: $(git -C "$SRC" rev-parse --short HEAD 2>/dev/null || echo '未知')"
echo "==> docker build $IMAGE"
docker build -t "$IMAGE" -f "$SRC/site/deploy/Dockerfile" "$SRC"

echo "==> 重启容器 $NAME (端口 $HOST_PORT -> 8000)"
docker rm -f "$NAME" 2>/dev/null || true
docker run -d --name "$NAME" --restart=always \
  -p "$HOST_PORT:8000" \
  -v "$APP_DIR/data:/app/site/backend/data" \
  -v "$APP_DIR/reports:/app/site/backend/reports" \
  --env-file "$ENV_FILE" \
  "$IMAGE"

echo "==> 健康检查"
for _ in $(seq 1 20); do
  sleep 2
  if curl -fsS "http://127.0.0.1:$HOST_PORT/health" >/dev/null 2>&1; then
    echo "OK ✅  http://<本机IP>:$HOST_PORT/"
    docker ps --filter "name=$NAME" --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
    exit 0
  fi
done
die "健康检查未通过，看日志: docker logs $NAME"
