#!/usr/bin/env bash
# 在本地开发机执行：构建前端 + 同步代码到服务器 + 重启后端。
# 用法：SERVER=root@<公网IP> ./site/deploy/sync.sh
set -euo pipefail

SERVER="${SERVER:?请设置 SERVER，例如 SERVER=root@1.2.3.4}"
REMOTE_DIR="/opt/zhisou/app"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

cd "$REPO_ROOT"

echo "==> 构建前端"
npm --prefix site/frontend install
npm --prefix site/frontend run build

echo "==> 同步到 $SERVER:$REMOTE_DIR"
# .env / data / node_modules / .git 不上传；dist 需要强制带上（被 .gitignore 忽略）
rsync -az --delete \
  --exclude='.git/' \
  --exclude='node_modules/' \
  --exclude='**/__pycache__/' \
  --exclude='.venv/' \
  --exclude='site/backend/.env' \
  --exclude='site/backend/data/' \
  --exclude='site/backend/reports/' \
  ./ "$SERVER:$REMOTE_DIR/"

echo "==> 重启后端并自检"
ssh "$SERVER" '
  set -e
  chown -R zhisou:zhisou /opt/zhisou/app
  /opt/zhisou/venv/bin/pip install -q -r /opt/zhisou/app/site/requirements.txt
  systemctl restart zhisou-backend
  sleep 2
  systemctl --no-pager --lines=0 status zhisou-backend
  curl -fsS http://127.0.0.1:8000/health && echo
  nginx -t && systemctl reload nginx
'
echo "==> 完成"
