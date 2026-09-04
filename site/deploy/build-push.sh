#!/usr/bin/env bash
###############################################################################
# 开发机：构建镜像并推到 Docker Hub（供目标机 pull-update.sh 拉取）
#
#   bash site/deploy/build-push.sh <tag>        # 例：bash site/deploy/build-push.sh weibo3
#
# 前置：docker login（账号 qiankunzhang0929）；在 deploy 分支执行（含前端 dist）。
###############################################################################
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

TAG="${1:?用法: bash site/deploy/build-push.sh <tag>}"
REPO="qiankunzhang0929/zhisou"

test -f site/frontend/dist/index.html || {
  echo "缺 site/frontend/dist —— 在 deploy 分支执行，或先 npm --prefix site/frontend run build && git add -f site/frontend/dist"
  exit 1
}

# 单架构 v2 manifest：目标机是老 Docker（CentOS7），不认 buildx 的 manifest list / attestation
docker build --platform linux/amd64 --provenance=false --sbom=false --output type=docker \
  -t "$REPO:$TAG" -f site/deploy/Dockerfile .

docker push "$REPO:$TAG"
echo
echo "已推送 $REPO:$TAG"
echo "目标机执行： TAG=$TAG bash ~/pull-update.sh"
