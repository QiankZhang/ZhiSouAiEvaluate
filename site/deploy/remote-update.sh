#!/usr/bin/env bash
###############################################################################
# 目标机（10.2.1.44 / search 用户 / 只有 Docker）一条命令更新：
#
#   bash /data1/zhisou/app/site/deploy/remote-update.sh [分支]
#
# 干的事：从 GitHub 拉指定分支（默认 deploy）的 tar 包 → 原子替换 /data1/zhisou/app
#         → docker build → 滚动重启容器。不动 zhisou.env 和 data/。
#
# 一次性前置（只做一次，之后不用再碰 token）：
#   1. GitHub 建 fine-grained PAT：仓库 ZhiSouAiEvaluate、Contents=Read-only、
#      有效期尽量长（如 1 年）。
#   2. echo '<那串 github_pat_...>' > /data1/zhisou/.gh_token && chmod 600 /data1/zhisou/.gh_token
#
# 出问题回滚：
#   cd /data1/zhisou && rm -rf app && mv app.old app && bash app/site/deploy/docker-run.sh
###############################################################################
set -euo pipefail

APP_DIR="${APP_DIR:-/data1/zhisou}"
REPO="${REPO:-QiankZhang/ZhiSouAiEvaluate}"
BRANCH="${1:-deploy}"
TOKEN_FILE="${TOKEN_FILE:-$APP_DIR/.gh_token}"

die() { echo "错误: $*" >&2; exit 1; }

[ -f "$TOKEN_FILE" ] || die "缺 $TOKEN_FILE —— 见本脚本头部「一次性前置」"
TOKEN="$(tr -d ' \t\r\n' < "$TOKEN_FILE")"
[ -n "$TOKEN" ] || die "$TOKEN_FILE 是空的"
command -v docker >/dev/null || die "没有 docker 命令"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "==> 下载 $REPO@$BRANCH"
code=$(curl -sS -L -w '%{http_code}' -o "$TMP/src.tgz" \
  -H "Authorization: Bearer $TOKEN" \
  "https://api.github.com/repos/$REPO/tarball/$BRANCH")
[ "$code" = "200" ] || { echo "下载失败 HTTP $code:"; head -c 400 "$TMP/src.tgz"; echo; exit 1; }

echo "==> 解压校验"
rm -rf "$APP_DIR/app.new"; mkdir -p "$APP_DIR/app.new"
tar xzf "$TMP/src.tgz" -C "$APP_DIR/app.new" --strip-components=1
[ -f "$APP_DIR/app.new/site/frontend/dist/index.html" ] \
  || die "包里没有 site/frontend/dist —— 确认拉的是 deploy 分支（不是 main）"
[ -f "$APP_DIR/app.new/site/deploy/docker-run.sh" ] || die "包结构异常，缺 docker-run.sh"

echo "==> 原子替换 $APP_DIR/app（旧版本留到 app.old）"
rm -rf "$APP_DIR/app.old"
[ -d "$APP_DIR/app" ] && mv "$APP_DIR/app" "$APP_DIR/app.old"
mv "$APP_DIR/app.new" "$APP_DIR/app"

echo "==> 构建并重启容器"
bash "$APP_DIR/app/site/deploy/docker-run.sh"

echo
echo "更新完成。回滚：cd $APP_DIR && rm -rf app && mv app.old app && bash app/site/deploy/docker-run.sh"
