#!/usr/bin/env bash
# 在全新 ECS 上以 root 执行一次（Alibaba Cloud Linux 3）。
# 前置：已用 sync.sh 把代码同步到 /opt/zhisou/app（或先 git clone 到该路径）。
set -euo pipefail

APP=/opt/zhisou/app
VENV=/opt/zhisou/venv

echo "==> 安装 nginx / python3.11"
dnf install -y nginx python3.11 python3.11-pip

echo "==> 创建服务账号与目录"
id -u zhisou &>/dev/null || useradd -r -M -d /opt/zhisou -s /sbin/nologin zhisou
mkdir -p "$APP" /opt/zhisou "$APP/site/backend/data" "$APP/site/backend/reports"

echo "==> 创建虚拟环境"
[ -d "$VENV" ] || python3.11 -m venv "$VENV"
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q -r "$APP/site/requirements.txt"

echo "==> 后端 .env"
if [ ! -f "$APP/site/backend/.env" ]; then
  cp "$APP/site/deploy/env.example" "$APP/site/backend/.env"
  echo "   已生成默认 .env（JUDGE_ENGINE=simulated），按需编辑"
fi

echo "==> systemd 服务"
cp "$APP/site/deploy/zhisou-backend.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable zhisou-backend

echo "==> nginx 站点"
rm -f /etc/nginx/conf.d/zhisou.conf
cp "$APP/site/deploy/nginx-zhisou.conf" /etc/nginx/conf.d/zhisou.conf
# 主配置里若已有 default_server，去掉该标记，避免与本站点冲突（我们的站点是 default_server）
sed -i 's/\(listen[^;]*\)\bdefault_server\b/\1/g' /etc/nginx/nginx.conf || true

echo "==> 权限与启动"
chown -R zhisou:zhisou /opt/zhisou
systemctl restart zhisou-backend
nginx -t
systemctl enable --now nginx
systemctl reload nginx

sleep 2
curl -fsS http://127.0.0.1:8000/health && echo
echo "==> 完成。浏览器访问 http://<公网IP>/"
