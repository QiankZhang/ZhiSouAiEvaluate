#!/usr/bin/env bash
###############################################################################
# 开发机上执行：把 main 最新同步到 deploy 分支（含前端重新构建）并推送。
#   bash site/deploy/publish-deploy.sh
# 之后到目标机 10.2.1.44 执行：
#   bash /data1/zhisou/app/site/deploy/remote-update.sh
#
# deploy 分支 = main + force-add 的 site/frontend/dist（目标机 CentOS 7 跑不了 Vite）。
###############################################################################
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

[ -z "$(git status --porcelain)" ] || { echo "工作区有未提交改动，先 commit 或 stash"; exit 1; }

git checkout main
git pull --ff-only

git checkout deploy
git pull --ff-only 2>/dev/null || true
git merge --no-edit main

if command -v npm >/dev/null 2>&1; then
  echo "==> 重新构建前端"
  npm --prefix site/frontend run build
  git add -f site/frontend/dist
  git diff --cached --quiet || git commit -m "build(deploy): 前端产物"
else
  echo "!! 本机无 npm：跳过前端重建。若本次改了前端，需在有 Node>=22.13 的机器上补做。"
fi

git push origin deploy
git checkout main
echo
echo "已推送 deploy 分支。目标机执行： bash /data1/zhisou/app/site/deploy/remote-update.sh"
