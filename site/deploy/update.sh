#!/usr/bin/env bash
###############################################################################
# 日常更新脚本 —— 服务器上以 root 执行
#
#   sudo bash /opt/zhisou/app/site/deploy/update.sh
#
# 做的事：拉取/同步新代码 -> 重装依赖 -> 重建前端 -> 重启后端 -> reload nginx -> 自检
# 不动 .env，不动 backend/data（用户数据）。
###############################################################################
set -euo pipefail

APP=/opt/zhisou/app
VENV=/opt/zhisou/venv
SVC_USER=zhisou

log() { printf '\033[36m==>\033[0m %s\n' "$*"; }
die() { printf '\033[31m错误:\033[0m %s\n' "$*" >&2; exit 1; }
[ "$(id -u)" = 0 ] || die "请用 root 或 sudo 运行"
[ -d "$APP" ] || die "$APP 不存在，请先执行 install.sh"

# ---- 1. 更新代码 ----
if [ -d "$APP/.git" ]; then
  log "git pull"
  git -C "$APP" pull --ff-only
else
  log "非 git 目录：请先把新版代码 rsync 到 $APP（保留 backend/.env 和 backend/data），再重跑本脚本"
fi

# ---- 2. 依赖 ----
log "更新 Python 依赖"
WHEELS="$APP/site/deploy/vendor/wheels"
if [ -d "$WHEELS" ]; then
  "$VENV/bin/pip" install -q --no-index --find-links "$WHEELS" -r "$APP/site/requirements.txt"
else
  "$VENV/bin/pip" install -q -r "$APP/site/requirements.txt"
fi

# ---- 3. 前端 ----
DIST="$APP/site/frontend/dist"
if command -v npm >/dev/null 2>&1; then
  log "重建前端"
  ( cd "$APP/site/frontend" && npm install --no-audit --no-fund && npm run build )
elif [ -f "$DIST/index.html" ]; then
  log "无 Node，沿用已带入的 dist（确保更新代码时一并同步了 site/frontend/dist）"
else
  die "无 Node 且无 dist，前端无法更新"
fi

# ---- 4. 重启 + 自检 ----
chown -R "$SVC_USER":"$SVC_USER" /opt/zhisou
systemctl restart zhisou-backend
nginx -t && systemctl reload nginx
sleep 2
curl -fsS http://127.0.0.1:8000/health >/dev/null \
  && log "更新完成 ✅" \
  || die "后端未就绪，查看: journalctl -u zhisou-backend -n 50"
