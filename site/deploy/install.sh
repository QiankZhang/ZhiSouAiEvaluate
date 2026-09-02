#!/usr/bin/env bash
###############################################################################
# 首次部署脚本 —— 在目标服务器上以 root 执行一次
#
#   sudo bash /opt/zhisou/app/site/deploy/install.sh
#
# 前置：本仓库已完整放到服务器某个目录（git clone 或解压发布包均可）。
# 幂等：可重复执行，不会破坏已有数据。
###############################################################################
set -euo pipefail

APP=/opt/zhisou/app
VENV=/opt/zhisou/venv
SVC_USER=zhisou
GATEWAY_DEFAULT="http://10.37.254.124:8010"

# 仓库根 = 本脚本所在目录的上两级
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

log() { printf '\033[36m==>\033[0m %s\n' "$*"; }
die() { printf '\033[31m错误:\033[0m %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" = 0 ] || die "请用 root 或 sudo 运行"

# ---- 1. 包管理器 ----
if   command -v dnf >/dev/null; then PM_INSTALL="dnf install -y"
elif command -v yum >/dev/null; then PM_INSTALL="yum install -y"
elif command -v apt-get >/dev/null; then apt-get update -qq; PM_INSTALL="apt-get install -y"
else die "未识别的包管理器（非 dnf/yum/apt），请手动装 nginx / python3.11 / rsync 后重跑"
fi

log "安装 nginx / python / rsync"
$PM_INSTALL nginx rsync >/dev/null || true
# RHEL 系单独提供 python3.11；Debian 系用自带 python3 + venv 包
$PM_INSTALL python3.11 python3.11-pip >/dev/null 2>&1 || true
$PM_INSTALL python3 python3-venv python3-pip  >/dev/null 2>&1 || true

# ---- 2. 找一个 >=3.10 的 python ----
PY=""
for c in python3.13 python3.12 python3.11 python3.10 python3; do
  command -v "$c" >/dev/null 2>&1 || continue
  if "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)'; then PY="$c"; break; fi
done
[ -n "$PY" ] || die "没有 Python >= 3.10（代码用了 3.10 的类型语法）。请先安装 python3.11 再重跑。"
log "使用 $PY ($($PY -V 2>&1))"

# ---- 3. 代码就位到 /opt/zhisou/app ----
if [ "$SRC" != "$APP" ]; then
  log "复制代码到 $APP"
  mkdir -p "$APP"
  rsync -a --delete \
    --exclude='.git/' --exclude='node_modules/' --exclude='**/__pycache__/' \
    --exclude='.venv/' \
    --exclude='site/backend/.env' \
    --exclude='site/backend/data/' \
    --exclude='site/backend/reports/' \
    "$SRC"/ "$APP"/
fi

# ---- 4. 服务账号与运行时目录 ----
id -u "$SVC_USER" &>/dev/null || useradd -r -M -d /opt/zhisou -s /sbin/nologin "$SVC_USER"
mkdir -p /opt/zhisou "$APP/site/backend/data" "$APP/site/backend/reports"

# ---- 5. Python 虚拟环境 + 依赖 ----
log "创建虚拟环境并安装依赖"
[ -d "$VENV" ] || "$PY" -m venv "$VENV"
"$VENV/bin/pip" install -q --upgrade pip
WHEELS="$APP/site/deploy/vendor/wheels"
if [ -d "$WHEELS" ]; then
  "$VENV/bin/pip" install -q --no-index --find-links "$WHEELS" -r "$APP/site/requirements.txt"
else
  "$VENV/bin/pip" install -q -r "$APP/site/requirements.txt" \
    || die "pip 安装失败。内网无法访问 PyPI 时，请在有网机器上执行 deploy/make-offline-bundle.sh 生成离线包后重试。"
fi

# ---- 6. 前端构建产物 ----
DIST="$APP/site/frontend/dist"
if [ -f "$DIST/index.html" ]; then
  log "使用随代码带来的前端构建产物 ($DIST)"
elif command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1; then
  log "服务器上构建前端"
  ( cd "$APP/site/frontend" && npm install --no-audit --no-fund && npm run build )
else
  die "没有前端构建产物，服务器也没有 Node(>=22.13)。请在有 Node 的机器上执行
       npm --prefix site/frontend install && npm --prefix site/frontend run build
     然后把 site/frontend/dist 一起传到服务器，再重跑本脚本。"
fi

# ---- 7. 后端 .env ----
ENV_FILE="$APP/site/backend/.env"
if [ ! -f "$ENV_FILE" ]; then
  cp "$APP/site/deploy/env.example" "$ENV_FILE"
  log "已生成 $ENV_FILE —— 请确认 LLM_BASE_URL 指向可达的网关，默认 $GATEWAY_DEFAULT"
fi

# ---- 8. systemd 服务 ----
log "安装 systemd 服务 zhisou-backend"
cp "$APP/site/deploy/zhisou-backend.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable zhisou-backend >/dev/null

# ---- 9. nginx 站点 ----
log "安装 nginx 站点"
rm -f /etc/nginx/conf.d/zhisou.conf
cp "$APP/site/deploy/nginx-zhisou.conf" /etc/nginx/conf.d/zhisou.conf
# 主配置里若已有 default_server 标记，去掉以免和本站点冲突
sed -i 's/\(listen[^;]*\)\bdefault_server\b/\1/g' /etc/nginx/nginx.conf 2>/dev/null || true

# ---- 10. 权限、启动、自检 ----
chown -R "$SVC_USER":"$SVC_USER" /opt/zhisou
systemctl restart zhisou-backend
nginx -t
systemctl enable --now nginx >/dev/null
systemctl reload nginx

sleep 2
if curl -fsS http://127.0.0.1:8000/health >/dev/null; then
  log "后端健康检查通过"
else
  die "后端未就绪，查看日志: journalctl -u zhisou-backend -n 50"
fi

# 网关连通性提示（不阻断安装）
GW="$(grep -E '^LLM_BASE_URL=' "$ENV_FILE" | cut -d= -f2- | sed 's#/v1/\?$##')"
GW="${GW:-$GATEWAY_DEFAULT}"
if curl -fsS -m 8 "$GW/v1/quota" >/dev/null 2>&1; then
  log "大模型网关可达: $GW"
else
  printf '\033[33m注意:\033[0m 连不到大模型网关 %s —— 真实评测不可用。\n' "$GW"
  printf '      打通内网路由后，把 %s 里的 JUDGE_ENGINE 改回 auto 并 systemctl restart zhisou-backend\n' "$ENV_FILE"
fi

IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
log "完成 ✅  浏览器访问 http://${IP:-<服务器IP>}/"
log "初始账号 = 姓名拼音(如 zhangqiankun)，初始密码 12345678，登录后请改密码"
