#!/usr/bin/env bash
# 在目标内网机器（如 10.2.1.44）上执行，检查是否具备部署条件。
# 不改动任何东西，只读检查。
set -u

GATEWAY="${GATEWAY:-http://10.37.254.124:8010}"
ok()   { printf '  \033[32m[OK]\033[0m   %s\n' "$*"; }
warn() { printf '  \033[33m[WARN]\033[0m %s\n' "$*"; }
bad()  { printf '  \033[31m[BAD]\033[0m  %s\n' "$*"; }

echo "== 操作系统 =="
if [ -r /etc/os-release ]; then . /etc/os-release; echo "  $PRETTY_NAME"; else uname -a; fi

echo "== Python（需 >= 3.10）=="
for py in python3.12 python3.11 python3.10 python3; do
  if command -v "$py" >/dev/null 2>&1; then
    v=$("$py" -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null)
    maj=${v%.*}; min=${v#*.}
    if [ "${maj:-0}" -eq 3 ] && [ "${min:-0}" -ge 10 ]; then ok "$py -> $v"; else warn "$py -> $v（低于 3.10）"; fi
  fi
done
command -v python3 >/dev/null 2>&1 || bad "未找到 python3"

echo "== venv 模块 =="
python3 -m venv --help >/dev/null 2>&1 && ok "python3 -m venv 可用" || warn "缺 venv，需要装 python3-venv / pythonX.Y"

echo "== nginx =="
if command -v nginx >/dev/null 2>&1; then ok "$(nginx -v 2>&1)"; else warn "未安装 nginx（部署时装）"; fi

echo "== 端口占用（80 / 8000）=="
if command -v ss >/dev/null 2>&1; then LST=$(ss -tlnp 2>/dev/null); else LST=$(netstat -tlnp 2>/dev/null); fi
echo "$LST" | grep -qE '[:.]80\b'   && warn "80 端口已被占用：$(echo "$LST" | grep -E '[:.]80\b')" || ok "80 端口空闲"
echo "$LST" | grep -qE '[:.]8000\b' && warn "8000 端口已被占用" || ok "8000 端口空闲"

echo "== 到大模型网关的连通性（$GATEWAY）=="
code=$(curl -s -o /tmp/_gw.$$ -w '%{http_code}' -m 8 "$GATEWAY/v1/quota" 2>/dev/null)
if [ "$code" = "200" ]; then ok "网关可达，/v1/quota 返回：$(cat /tmp/_gw.$$)"
elif [ -n "$code" ] && [ "$code" != "000" ]; then warn "网关有响应但 HTTP $code：$(cat /tmp/_gw.$$)"
else bad "连不到网关（超时/无路由）——内网部署的前提不成立，需先打通路由"
fi
rm -f /tmp/_gw.$$

echo "== 资源 =="
echo "  CPU  : $(nproc 2>/dev/null || getconf _NPROCESSORS_ONLN) 核"
command -v free >/dev/null 2>&1 && echo "  内存 : $(free -m | awk '/Mem:/{print $2" MiB 总 / "$7" MiB 可用"}')"
echo "  磁盘 : $(df -h / | awk 'NR==2{print $4" 可用 / "$2" 总"}')"

echo "== 权限 =="
if [ "$(id -u)" = 0 ]; then ok "当前是 root"
elif sudo -n true 2>/dev/null; then ok "有免密 sudo"
else warn "需要 sudo 权限（部署时装包、写 systemd/nginx）"
fi

echo "== Node（前端构建，需 >= 22.13；可在别处构建后传 dist）=="
if command -v node >/dev/null 2>&1; then ok "$(node --version)"; else warn "无 node，本地构建好 frontend/dist 再传"; fi

echo
echo "关注 [BAD] / [WARN] 项。最关键：网关连通性、Python>=3.10、80 端口。"
