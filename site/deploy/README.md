# 智搜效果评估平台 · 部署与运维手册

> 给接手部署的开发同学。这套脚本让首次部署和日常更新各自一条命令搞定。
>
> **选哪种方式：**
> - 目标机能装 Python ≥ 3.10、有 root/sudo、能装 nginx → 用下面的 `install.sh`（方式 A/B）。
> - 目标机没有 root、没有 Python、只有 Docker（公司 CentOS 7 通道机就是这种）→ 见 **[DOCKER.md](DOCKER.md)**，`git clone` + `docker-run.sh` 一条命令。

## 一、这是个什么系统

| | |
| --- | --- |
| 前端 | React + Vite，构建成纯静态文件（`site/frontend/dist`），由 nginx 托管 |
| 后端 | FastAPI，单进程 `uvicorn`，监听 `127.0.0.1:8000` |
| 数据库 | **内嵌 SQLite**，单文件 `site/backend/data/app.db`（含业务数据 + 账号）。无独立 DB 服务 |
| 反向代理 | nginx :80 → 静态资源 + `/api` 反代到后端 |
| 外部依赖 | **大模型网关**（OpenAI 兼容），默认 `http://10.37.254.124:8010`，见仓库根 `API.md` |

架构图：

```
浏览器 ──:80──> nginx ──┬─ /              静态文件  site/frontend/dist
                        └─ /api, /health  反代 127.0.0.1:8000 (uvicorn)
                                              │
                                              └──> 大模型网关 10.37.254.124:8010
```

## 二、部署前提（务必先确认）

1. **服务器能连到大模型网关** `10.37.254.124:8010` —— 这是整套系统能做真实评测的前提。
   在服务器上 `curl http://10.37.254.124:8010/v1/quota` 能返回 JSON 即可。
   连不通也能部署（`.env` 里 `JUDGE_ENGINE=simulated`），但只有模拟打分。
2. **Python ≥ 3.10**（代码用了 3.10 的类型语法）。RHEL/Alibaba Cloud Linux 系装 `python3.11` 即可。
3. **80 端口空闲**（或告知需要共用 nginx / 换端口，改 `nginx-zhisou.conf`）。
4. 资源：2 vCPU / 2 GiB 内存 / 20–40 GiB 磁盘足够。
5. 先跑 `preflight.sh` 自检（只读，不改任何东西）：
   ```bash
   bash site/deploy/preflight.sh
   ```

## 三、首次部署

### 方式 A：服务器能上外网 / 有内网 PyPI 镜像和 Node

```bash
# 1. 把代码放到服务器（git clone 或 scp 都行），目录随意
git clone <仓库地址> zhisou && cd zhisou
# 2. 一条命令
sudo bash site/deploy/install.sh
```

### 方式 B：内网服务器完全离线（推荐）

在**有外网 + Node ≥ 22.13** 的机器上打发布包（最好是一台 x86_64 Linux，和目标服务器同架构）：

```bash
bash site/deploy/make-release.sh
# 产出 dist/zhisou-release-<日期>.tar.gz（含前端构建产物 + 离线依赖 wheels）
# 目标机器不是 x86_64/py3.11 时: TARGET_PLATFORM=... TARGET_PY=... bash site/deploy/make-release.sh
```

拷到内网服务器：

```bash
tar xzf zhisou-release-<日期>.tar.gz
sudo bash zhisou/site/deploy/install.sh
```

`install.sh` 会：装 nginx/python → 建 `zhisou` 服务账号和虚拟环境 → 装依赖 →
用（或构建）前端 → 生成 `backend/.env` → 装 systemd 服务和 nginx 站点 → 启动 + 健康检查。
**幂等**，可重复执行。

部署完成后浏览器访问 `http://<服务器IP>/`。
初始账号 = 姓名拼音（如 `zhangqiankun`），初始密码 `12345678`，登录后立即改密码。

## 四、配置 `.env`

文件在 `/opt/zhisou/app/site/backend/.env`（不进版本库）。改完 `sudo systemctl restart zhisou-backend` 生效。

```ini
# 网关可达时：
JUDGE_ENGINE=auto
LLM_BASE_URL=http://10.37.254.124:8010/v1
LLM_MODEL=deepseek-v4-flash
JUDGE_CONCURRENCY=4

# 网关暂不可达时先用：
# JUDGE_ENGINE=simulated
```

完整可选项见仓库根 `site/backend/README.md`。

## 五、日常更新

```bash
sudo bash /opt/zhisou/app/site/deploy/update.sh
```

拉新代码 → 重装依赖 → 重建前端 → 重启后端 → reload nginx → 健康检查。
**不动** `.env` 和 `backend/data`（用户数据）。

离线服务器：先把新版代码（含 `site/frontend/dist`）rsync 到 `/opt/zhisou/app`，
注意排除 `backend/.env` 和 `backend/data/`，再跑 `update.sh`。

## 六、运维

```bash
sudo systemctl status zhisou-backend        # 状态
sudo journalctl -u zhisou-backend -f        # 后端日志
sudo systemctl restart zhisou-backend       # 重启后端
sudo nginx -t && sudo systemctl reload nginx

# 备份（业务数据 + 账号都在这一个目录）
bash /opt/zhisou/app/site/deploy/backup.sh
# 建议 cron: 0 3 * * * bash /opt/zhisou/app/site/deploy/backup.sh >/dev/null 2>&1

# 清库重来（会删掉所有任务/数据集/账号）
sudo systemctl stop zhisou-backend
sudo rm /opt/zhisou/app/site/backend/data/app.db*
sudo systemctl start zhisou-backend
```

## 七、注意事项

- **后端必须单进程**：SQLite 持久化是「整份内存状态定时快照」，多开 uvicorn worker 或多实例会互相覆盖。systemd 单元已固定单进程，不要加 `--workers`。
- 迁移老数据：把旧的 `backend/data/app.db*`（三个文件）拷到新服务器同目录，启动自动读回。
- 加域名 / HTTPS：解析 A 记录到服务器，`nginx-zhisou.conf` 改 `server_name`，`certbot --nginx` 签证书。
- 端口/路径冲突：`nginx-zhisou.conf` 是标准 nginx server 块，可按需改 `listen` 或挪到子路径。

## 八、目录约定

| 路径 | 用途 |
| --- | --- |
| `/opt/zhisou/app` | 代码 |
| `/opt/zhisou/venv` | Python 虚拟环境 |
| `/opt/zhisou/app/site/backend/data/` | SQLite 数据（**备份对象**） |
| `/opt/zhisou/backup/` | `backup.sh` 默认输出 |
| `/etc/systemd/system/zhisou-backend.service` | 后端服务单元 |
| `/etc/nginx/conf.d/zhisou.conf` | nginx 站点 |
