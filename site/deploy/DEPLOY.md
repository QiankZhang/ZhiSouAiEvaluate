# 部署手册 · 阿里云 ECS（原生 systemd + nginx）

架构：nginx 静态托管 `frontend/dist` + 反代 `/api` → 本机 `uvicorn`(127.0.0.1:8000)，
FastAPI 单进程，数据落 SQLite（`site/backend/data/app.db`）。对外仅开 80 端口。

---

## 1. 购买 ECS（你自己在控制台点「立即购买」，我不代操作）

截图里的配置基本可用，下单前确认：

| 项 | 建议 |
| --- | --- |
| 实例规格 | `ecs.e-c1m1.large` 2C2G 经济型 e —— 够用 |
| 镜像 | Alibaba Cloud Linux 3.2104 LTS 64 位 |
| 系统盘 | ESSD Entry 40 GiB —— 够用 |
| 地域 | **若之后要打通内网大模型网关，选网关所在地域/VPC**；否则就近即可 |
| **公网 IP** | 截图未显示，务必往下滚勾选「分配公网 IPv4 地址」，带宽按量或 1–3 Mbps 固定 |
| 登录凭证 | 设置 root 密码或绑定 SSH 密钥对 |
| 安全组 | 见下 |

**安全组入方向规则：**

| 端口 | 源 | 用途 |
| --- | --- | --- |
| 22 | 你的办公/家庭出口 IP（不要 0.0.0.0/0） | SSH |
| 80 | 0.0.0.0/0 | HTTP |
| 443 | 0.0.0.0/0 | 以后配域名/HTTPS 再用 |

> 大模型网关 `http://10.37.254.124:8010` 是内网地址，公网 ECS 默认连不到。
> 打通前先跑模拟引擎（`JUDGE_ENGINE=simulated`），真实评测暂不可用。

---

## 2. 首次部署

在**本地开发机**（已装 Node ≥ 22.13、rsync、ssh）：

```bash
cd /Users/sunyingying/Desktop/ZhiSouAiEvaluate
export SERVER=root@<公网IP>

# 2.1 先把代码推上去（会顺带构建前端）
./site/deploy/sync.sh

# 2.2 登录服务器跑一次初始化
ssh $SERVER 'bash /opt/zhisou/app/site/deploy/server-setup.sh'
```

`server-setup.sh` 做的事：装 nginx + python3.11、建 `zhisou` 服务账号、建 venv 装依赖、
生成 `backend/.env`（默认 `JUDGE_ENGINE=simulated`）、装并启用 systemd 服务、写 nginx 站点。

完成后浏览器打开 `http://<公网IP>/`。

**初始登录**：账号为姓名拼音（如 `zhangqiankun`），初始密码 `12345678`，首次登录后请改密码。

---

## 3. 日常更新

改完代码后，本地一条命令：

```bash
SERVER=root@<公网IP> ./site/deploy/sync.sh
```

会重新构建前端、rsync、`pip install`、重启 `zhisou-backend`、reload nginx，并做 `/health` 自检。

---

## 4. 运维

```bash
systemctl status zhisou-backend
journalctl -u zhisou-backend -f          # 后端日志
systemctl restart zhisou-backend
nginx -t && systemctl reload nginx
```

**数据备份**（SQLite，全部业务数据 + 账号都在这里）：

```bash
ssh $SERVER 'tar czf - -C /opt/zhisou/app/site/backend data' > zhisou-data-$(date +%F).tgz
```

**清库重来**：`rm /opt/zhisou/app/site/backend/data/app.db*` 后重启服务。

---

## 5. 打通内网网关后

编辑 `/opt/zhisou/app/site/backend/.env`：

```
JUDGE_ENGINE=auto
LLM_BASE_URL=http://10.37.254.124:8010/v1
LLM_MODEL=deepseek-v4-flash
```

`systemctl restart zhisou-backend`。验证：`curl http://10.37.254.124:8010/v1/quota`（在服务器上）能通。

---

## 6. 以后加域名 + HTTPS

1. 域名解析 A 记录 → 公网 IP，安全组放行 443。
2. `dnf install -y certbot python3-certbot-nginx`
3. 改 `nginx-zhisou.conf` 的 `server_name` 为域名，`nginx -s reload`
4. `certbot --nginx -d your.domain` 自动签发并配置跳转。
