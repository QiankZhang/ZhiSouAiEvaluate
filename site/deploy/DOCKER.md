# Docker 单容器部署（目标机无 root / 无 Python，只有 Docker）

适用：公司 CentOS 7 通道机（如 `10.2.1.44`）。以 `search` 用户操作，全程不需要 root。
一个容器同时跑后端 API 和前端静态资源（FastAPI 直接托管 `site/frontend/dist`）。

```
浏览器 ──:8080──> docker 容器 ┌─ /              前端静态 (site/frontend/dist)
                              ├─ /api, /health  FastAPI (uvicorn :8000)
                              └──> 大模型网关 10.37.254.124:8010
                        SQLite: /data1/zhisou/data/app.db  ← volume 挂载，容器重建不丢
```

## 目录约定

| 路径 | 用途 |
| --- | --- |
| `/data1/zhisou/app` | `git clone` 的代码（**deploy 分支**，含 `site/frontend/dist`） |
| `/data1/zhisou/zhisou.env` | 运行配置（不进版本库） |
| `/data1/zhisou/data/` | SQLite 数据（**备份对象**，含账号） |
| `/data1/zhisou/reports/` | 报告导出缓存 |
| 容器 `zhisou` | `--restart=always`，开机自启 |

## 首次部署

```bash
# 1. 建目录
mkdir -p /data1/zhisou && cd /data1/zhisou

# 2. 拉代码（deploy 分支带前端构建产物）。私有库要 GitHub 用户名 + PAT。
git clone --branch deploy --depth 1 https://github.com/QiankZhang/ZhiSouAiEvaluate.git app
cd app && git remote set-url origin https://github.com/QiankZhang/ZhiSouAiEvaluate.git && cd ..

# 3. 配置
cp app/site/deploy/zhisou.env.example zhisou.env
#   默认 JUDGE_ENGINE=auto + 网关 10.37.254.124:8010（该机可直连），一般不用改

# 4. 构建 + 启动 + 健康检查（首次和以后更新都跑这个）
bash app/site/deploy/docker-run.sh
```

默认监听宿主机 `8080` 端口。要换端口：`HOST_PORT=9000 bash app/site/deploy/docker-run.sh`。

浏览器访问 `http://10.2.1.44:8080/`，种子账号见仓库根 `组织与账号系统设计.md`（如 `zhangqiankun` / `12345678`），登录后立即改密码。

## 日常更新

```bash
cd /data1/zhisou/app && git pull
bash site/deploy/docker-run.sh
```

`docker-run.sh` 会重新 `docker build` 并滚动重启容器，**不动** `zhisou.env` 和 `data/`。
前端改动需要在有 Node ≥ 22.13 的机器上重新 `npm --prefix site/frontend run build` 后把 `dist/` 推到 deploy 分支（CentOS 7 跑不了现代 Vite）。

## 运维

```bash
docker logs -f zhisou                      # 日志
docker restart zhisou                      # 重启
docker ps --filter name=zhisou             # 状态
curl -s localhost:8080/health              # 健康检查

# 备份（数据 + 账号都在这一个目录）
tar czf /data1/zhisou/backup-$(date +%F).tgz -C /data1/zhisou data
# 建议 crontab: 0 3 * * * tar czf /data1/zhisou/backup-$(date +\%F).tgz -C /data1/zhisou data

# 清库重来（删掉所有任务/数据集/账号）
docker rm -f zhisou
rm -f /data1/zhisou/data/app.db*
bash /data1/zhisou/app/site/deploy/docker-run.sh
```

## 注意事项

- **单进程**：SQLite 持久化是「整份内存状态定时快照」，不要在容器里加 `--workers` 或起多个容器。
- **数据文件属主**：容器内以 root 写盘，宿主机 `data/` 下的 `app.db*` 属主是 root；`search` 用户备份用 `tar`（能读）没问题，直接 `cp` 可能需要 `sudo`。
- **网关连通性**：容器走默认 bridge 网络即可访问内网 `10.37.254.124:8010`。若不通，`zhisou.env` 改 `JUDGE_ENGINE=simulated` 先上线（只有模拟打分）。
- **对外访问**：容器只在目标机本地开 `8080`。从办公网访问需要公司内网路由 / SLB / 域名映射到 `10.2.1.44:8080`，这一步走公司 OPS 流程，不在本脚本范围。
- **基础镜像**：`docker-run.sh` 默认 `docker.m.daocloud.io/library/python:3.11-slim-bullseye`。
  - Docker Hub 在公司网络不可达，daocloud 镜像源实测可用；换源用 `BASE_IMAGE=... bash docker-run.sh`。
  - **必须 bullseye**（Debian 11）：CentOS 7 自带的老 Docker（19.03 era）seccomp 白名单不含 `clone3`，
    Debian 12（bookworm，glibc 2.36）基础镜像在容器内起线程会报 `RuntimeError: can't start new thread`。
    bullseye 是 glibc 2.31，用老的 `clone()`，没这问题。
  - 另一条路（不换基础镜像）：给 build 和 run 都加 `--security-opt seccomp=unconfined`，但会削弱容器隔离。
