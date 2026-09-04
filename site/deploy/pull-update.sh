#!/bin/bash
###############################################################################
# 目标机拉镜像更新（外网到 GitHub / PyPI 不通时用这个，不本地构建）
#
#   开发机：bash site/deploy/build-push.sh <tag>      # 构建 + 推 Docker Hub
#   目标机：M=docker.1ms.run TAG=<tag> bash ~/pull-update.sh
#
# 原理：目标机连不上 registry-1.docker.io，但连得上国内 Docker Hub 代理
#      （docker.1ms.run / docker.1panel.live 等，daocloud 有白名单不行）。
###############################################################################
set -e

REPO="${REPO:-qiankunzhang0929/zhisou}"
TAG="${TAG:?用法: TAG=weibo3 [M=docker.1ms.run] bash pull-update.sh}"
M="${M:-docker.1ms.run}"          # Docker Hub 国内代理前缀
SRC="$M/$REPO:$TAG"

echo "==> 拉取 $SRC"
docker pull "$SRC"

echo "==> 切换镜像 + 滚动重启"
docker tag zhisou:latest zhisou:prev 2>/dev/null || true
docker tag "$SRC" zhisou:latest
docker rm -f zhisou 2>/dev/null || true
docker run -d --name zhisou --restart=always -p 8080:8000 \
  -v /data1/zhisou/data:/app/site/backend/data \
  -v /data1/zhisou/reports:/app/site/backend/reports \
  --env-file /data1/zhisou/zhisou.env \
  zhisou:latest

sleep 6
echo "==> 健康检查"
curl -s localhost:8080/health && echo
echo "回滚: docker rm -f zhisou && docker tag zhisou:prev zhisou:latest && (重跑上面的 docker run)"
