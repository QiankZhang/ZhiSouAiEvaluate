# 10.2.1.44 部署 / 更新速查

> 目标机 = 公司通道机后面的机器，只有 Docker（无 root、无 Python）。
> 应用以单个 Docker 容器运行：一个容器同时提供前端页面和后端 API。
> 详细背景见 [DOCKER.md](DOCKER.md)。
>
> **`bash ~/zhisou-update.sh` 卡在下载 / pip 连不上 pypi？** 目标机外网不稳，改走镜像中转，见
> [UPDATE-OFFLINE.md](UPDATE-OFFLINE.md)（开发机 `build-push.sh` 推 Docker Hub → 目标机 `pull-update.sh` 走国内代理拉）。

## 0. 现状

| 项 | 值 |
| --- | --- |
| 访问地址 | `http://10.2.1.44:8080/`（本机可访问；办公网需 OPS 配内网路由/域名） |
| 容器 | `zhisou`，`--restart=always`，端口 `8080->8000` |
| 配置 | `/data1/zhisou/zhisou.env`（不进版本库，更新不覆盖；`rw-rw-r--` 谁都能读） |
| 数据 | `/data1/zhisou/data/`（SQLite，含账号；更新不动；**备份对象**。bind mount，容器内 root 读写，不受宿主属主限制） |
| 目录属主 | `/data1/zhisou/*` 全属 **`jilin5`**（不是文档老版本写的 `search`） |
| 仓库 | `QiankZhang/ZhiSouAiEvaluate` 已 **public** —— 拉代码不需要 token |
| 初始账号 | 姓名拼音（如 `zhangqiankun`）/ `12345678`，登录后改密 |

登录目标机：通道机 `ssh qiankun1@dx1.c.sina.com` →（密码 + 统一认证）→ `>>>` 输 `10.2.1.44` →
`sudo -su search`（输 `qiankun1` 的统一认证密码）。`search` 在 `docker` 组、能读 `zhisou.env`，
但**不是 `/data1/zhisou` 的属主、读不到 `.gh_token`**，所以只能走下面第 1 节的 search 路径。

---

## 1. 用 `search` 账号更新（当前实际可用）

### 1.1 一次性：装脚本（只做一次）

登进目标机、`sudo -su search` 后，把 `search-update.sh` 存到家目录（一整行粘一次）：

```bash
curl -fsSL -o ~/zhisou-update.sh https://raw.githubusercontent.com/QiankZhang/ZhiSouAiEvaluate/deploy/site/deploy/search-update.sh && chmod +x ~/zhisou-update.sh
```

> 拉不到 raw 时用 codeload 兜底：先 `bash <(curl -fsSL https://codeload.github.com/QiankZhang/ZhiSouAiEvaluate/tar.gz/refs/heads/deploy | tar xz -O --wildcards '*/site/deploy/search-update.sh')` 一次性跑，再从解压目录 `cp` 出来。

### 1.2 日常更新

本地把 `main` 合进 `deploy`、重建前端并 push（见第 3 节），然后目标机 `search` 下：

```bash
bash ~/zhisou-update.sh
```

干的事：`~/zhisou-build` 里拉 `deploy` 分支 tar 包 → `docker build` → 备份旧镜像为 `zhisou:prev`
→ 滚动重启容器（复用 `/data1/zhisou/data`、`reports`、`zhisou.env`）→ 健康检查。**不碰 `jilin5` 的任何文件。**

### 1.3 回滚

```bash
docker rm -f zhisou && docker tag zhisou:prev zhisou:latest && docker run -d --name zhisou --restart=always -p 8080:8000 -v /data1/zhisou/data:/app/site/backend/data -v /data1/zhisou/reports:/app/site/backend/reports --env-file /data1/zhisou/zhisou.env zhisou:latest
```

---

## 2. 官方 `remote-update.sh`（仅当你能 `sudo -su jilin5` 或本身是目录属主时）

前置一次性：`echo 'github_pat_...' > /data1/zhisou/.gh_token && chmod 600 ...`（PAT：仓库
`ZhiSouAiEvaluate`、Contents=Read-only）。之后目标机：

```bash
bash /data1/zhisou/app/site/deploy/remote-update.sh
```

拉 `deploy` 分支 tar 包 → 原子替换 `/data1/zhisou/app`（旧版留 `app.old`）→ `docker build`
→ 滚动重启 → 健康检查。回滚：`cd /data1/zhisou && rm -rf app && mv app.old app && bash app/site/deploy/docker-run.sh`。

> 目前登录只能到 `search`，`search` 不是 `/data1/zhisou` 属主也读不到 `.gh_token` ——
> 所以**实际走第 1 节**。本节留作 `jilin5`/OPS 接手时的参考。

---

## 3. 开发机侧：把改动推到 `deploy` 分支

后端 / 前端改动推 `main` 后：

```bash
git checkout deploy && git merge main
npm --prefix site/frontend run build            # 前端有改动时才需要，dist 必须在有 Node≥22.13 的机器上构建
git add -f site/frontend/dist && git commit -m "build(deploy): 前端产物"
git push origin deploy
git checkout main
```

也可以直接 `bash site/deploy/publish-deploy.sh` 一把做完。之后目标机 `bash ~/zhisou-update.sh`（第 1 节）。

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

# 清库重来（删掉所有任务/数据集/账号）—— data 目录属 jilin5，search 删不掉 app.db，
# 只能在容器内删：
docker exec zhisou sh -c 'rm -f /app/site/backend/data/app.db*' && docker restart zhisou
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
| `remote-update.sh` 报 `.gh_token: Permission denied` / 无法替换 `app` | 登录到的是 `search`，`/data1/zhisou` 属 `jilin5`，`search` 不是属主也读不到 token | 走第 1 节 `~/zhisou-update.sh`（search 家目录构建，不碰 jilin5 文件；仓库已 public 免 token） |
| `sudo -su jilin5` 密码不对 | 没有 `jilin5` 密码，`qiankun1` 也没 sudo 到 jilin5 的权限 | 同上，走第 1 节；要 `jilin5` 权限找 OPS |
