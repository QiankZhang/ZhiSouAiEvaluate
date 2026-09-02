# 10.2.1.44 部署 / 更新速查

> 目标机 = 公司 CentOS 7 通道机机器，`search` 用户，只有 Docker（无 root、无 Python、git 太老）。
> 应用以单个 Docker 容器运行：一个容器同时提供前端页面和后端 API。
> 详细背景见 [DOCKER.md](DOCKER.md)。

## 0. 现状

| 项 | 值 |
| --- | --- |
| 访问地址 | `http://10.2.1.44:8080/`（本机可访问；办公网需 OPS 配内网路由/域名） |
| 容器 | `zhisou`，`--restart=always` |
| 代码 | `/data1/zhisou/app`（GitHub `deploy` 分支的快照，含前端构建产物） |
| 配置 | `/data1/zhisou/zhisou.env`（不进版本库，更新不覆盖） |
| 数据 | `/data1/zhisou/data/`（SQLite，含账号；更新不动；**备份对象**） |
| 初始账号 | 姓名拼音（如 `zhangqiankun`）/ `12345678`，登录后改密 |

登录目标机：通道机 `ssh qiankun1@dx1.c.sina.com` →（密码 + 统一认证）→ `>>>` 输 `10.2.1.44` → `sudo -su search`。

---

## 1. 一次性设置（只做一次）

在目标机以 `search` 用户：

```bash
# GitHub 建 fine-grained PAT：仓库 ZhiSouAiEvaluate、Contents=Read-only、有效期设 1 年，
# 复制那串 github_pat_...，然后：
echo 'github_pat_你的token' > /data1/zhisou/.gh_token
chmod 600 /data1/zhisou/.gh_token
```

`.gh_token` 在 `app/` 目录之外，更新时不会被覆盖，之后再也不用手动输 token。

> 拉不到基础镜像时先 `docker pull docker.m.daocloud.io/library/python:3.11-slim-bullseye`（首次已拉过）。

---

## 2. 日常更新（改了后端 / 只改文档）

后端代码推到 GitHub `main` 后，把 `main` 合进 `deploy` 分支并推送（`dist` 不用重建），
然后在目标机：

```bash
bash /data1/zhisou/app/site/deploy/remote-update.sh
```

一条命令：拉 `deploy` 分支 tar 包 → 原子替换 `/data1/zhisou/app`（旧版留 `app.old`）→
`docker build` → 滚动重启容器 → 健康检查。**不动** `zhisou.env` 和 `data/`。

---

## 3. 改了前端

CentOS 7 跑不了现代 Vite，前端必须在**有 Node ≥ 22.13 的机器**（如本地开发机）上构建后推 `deploy` 分支：

```bash
# 开发机上
git checkout deploy && git merge main
npm --prefix site/frontend run build
git add -f site/frontend/dist && git commit -m "build(deploy): 前端产物"
git push origin deploy
git checkout main
```

然后目标机照样 `bash /data1/zhisou/app/site/deploy/remote-update.sh`。

---

## 4. 回滚

```bash
cd /data1/zhisou && rm -rf app && mv app.old app && bash app/site/deploy/docker-run.sh
```

---

## 5. 运维

```bash
docker logs -f zhisou                                   # 日志
docker restart zhisou                                   # 重启
docker ps --filter name=zhisou                          # 状态
curl -s localhost:8080/health                           # 健康检查
docker exec zhisou python -c "import urllib.request;print(urllib.request.urlopen('http://10.37.254.124:8010/v1/quota',timeout=8).status)"  # 网关连通

# 备份（数据 + 账号都在这一个目录）
tar czf /data1/zhisou/backup-$(date +%F).tgz -C /data1/zhisou data

# 清库重来（删掉所有任务/数据集/账号）
docker rm -f zhisou && rm -f /data1/zhisou/data/app.db* && bash /data1/zhisou/app/site/deploy/docker-run.sh
```

---

## 6. 配置项 `zhisou.env`

改完重跑 `docker-run.sh`（或 `remote-update.sh`）生效。

```ini
JUDGE_ENGINE=auto                               # 真实评测；临时只看模拟改 simulated
LLM_BASE_URL=http://10.37.254.124:8010/v1       # 该机可直连，实测 /v1/quota=200
LLM_MODEL=deepseek-v4-flash
JUDGE_CONCURRENCY=4
```

---

## 7. 踩过的坑（换机 / 换人接手时看这里）

| 现象 | 原因 | 解法（已固化进脚本） |
| --- | --- | --- |
| `git clone` 报 `result=35 / SSL` | CentOS 7 自带 git 1.8.3.1 太老，连不上 GitHub TLS | 不用 git，用 `curl .../tarball/<分支>` 下 tar 包（`remote-update.sh` 就是这么做的） |
| `docker pull python:...` 超时 | 公司网络到 Docker Hub 不通 | 用 `docker.m.daocloud.io/library/...` 镜像源（`docker-run.sh` 默认） |
| `pip install` 报 `RuntimeError: can't start new thread` | CentOS 7 老 Docker 的 seccomp 不放行 Debian 12(glibc 2.36) 的 `clone3` | 基础镜像用 `-slim-bullseye`（Debian 11 / glibc 2.31，`docker-run.sh` 默认） |
| 粘贴多行命令在终端里断行 / 丢引号 | Cursor 集成终端的粘贴问题 | 命令写成单行 |
| 办公网打不开 `10.2.1.44:8080` | 通道机禁端口转发，笔记本无到该内网 IP 的路由 | 提 OPS 工单：内网域名 / SLB 指到 `10.2.1.44:8080` |
