# 目标机外网不通时的部署方法论

> 场景：`10.2.1.44` 到 **GitHub / PyPI 时好时坏或不通**（DNS 只返回 IPv6、大文件下载中途卡死、
> `registry-1.docker.io` 超时），但到 **新浪内网** 和 **国内 CDN / 镜像源** 正常。
> 2026-09 部署「博文数据集」时踩通，沉淀为标准流程。

## TL;DR 决策树

```
能 bash ~/zhisou-update.sh 成功？                → 用它（拉 deploy 分支本地构建）
  └─ 否：codeload 下载卡 / pip 连不上 pypi.org
       └─ 走「镜像中转」：开发机构建 → 推 Docker Hub → 目标机走国内代理拉
```

**永远不要**在目标机上跟 GitHub 大文件下载或 PyPI 较劲——它连得上根路径（HTTP 200）不代表扛得住几十 MB 传输。

## 一、镜像中转（当前标准做法）

### 开发机

```bash
git checkout deploy && git merge --no-edit main
npm --prefix site/frontend run build && git add -f site/frontend/dist
git commit -m "build(deploy): ..." && git push origin deploy   # SSH 抽风就 for 循环重试

bash site/deploy/build-push.sh <tag>        # 例 weibo3 —— 构建 linux/amd64 单架构 + 推 Docker Hub
```

镜像仓库 `qiankunzhang0929/zhisou`（**公开**，匿名可拉）。`build-push.sh` 用
`--platform linux/amd64 --provenance=false --sbom=false --output type=docker`——
目标机是 CentOS7 老 Docker，不认 buildx 的 manifest list / attestation。

### 目标机（search 账号）

一次性装脚本：
```bash
curl -fsSL -o ~/pull-update.sh https://raw.githubusercontent.com/QiankZhang/ZhiSouAiEvaluate/deploy/site/deploy/pull-update.sh && chmod +x ~/pull-update.sh
# 拉不到就手敲，内容见仓库 site/deploy/pull-update.sh（就十几行）
```

每次更新：
```bash
TAG=<tag> bash ~/pull-update.sh
```

## 二、可用 / 不可用的镜像源（实测 2026-09）

| 用途 | 地址 | 结果 |
| --- | --- | --- |
| Docker Hub 代理 | `docker.1ms.run` | ✅ 可拉个人仓库（慢但稳，别加 `timeout`） |
| Docker Hub 代理 | `docker.1panel.live` | ✅ 同上 |
| Docker Hub 代理 | `docker.m.daocloud.io` | ❌ **有白名单**，个人仓库拒绝；只 base 镜像能用 |
| Docker Hub 代理 | `docker.nju.edu.cn` | ❌ 403（限内网） |
| Docker Hub 代理 | `dockerpull.org` / `docker.registry.cyou` / `hub.rat.dev` | ❌ 超时 / 降级 |
| 直连 | `registry-1.docker.io` | ❌ 超时 |
| pip 镜像 | `https://mirrors.aliyun.com/pypi/simple/` | ✅ HTTP/2 200，`--build-arg PIP_INDEX_URL=` 用它 |
| base 镜像 | `docker.m.daocloud.io/library/python:3.11-slim-bullseye` | ✅（Dockerfile 默认） |
| 源码 tar | `codeload.github.com` | ⚠️ 根路径 200，实际 35MB tar 常中途卡死 |

诊断一条龙（目标机跑，看哪些能通）：
```bash
for h in mirrors.aliyun.com docker.m.daocloud.io docker.1ms.run docker.1panel.live github.com codeload.github.com; do
  printf "%-28s " "$h"; ip=$(getent hosts "$h"|awk 'NR==1{print $1}')
  [ -z "$ip" ] && { echo NO-DNS; continue; }
  echo "$ip http=$(curl -s -o /dev/null -m 10 -w '%{http_code}' https://$h/)"
done
```

## 三、把外部流水线（qinglong 类）打进镜像的方法论

「博文数据集」要调 qinglong（异步、依赖新浪内网 + aiohttp/redis/pandas/tqdm、原本跑在
`/data1/minisearch/...` 的专用 Python 环境）。目标机无 Python、无 qinglong，但**容器网络到新浪内网通**
（`getdata.search.weibo.com`、redis `rm51798` 都可达）。做法：

1. **vendored 进仓库** `qinglong/`（去掉 `logs/ data/ results/` 运行产物），Dockerfile `COPY qinglong /app/qinglong`。
2. **依赖单列** `site/deploy/requirements-weibo.txt`，Dockerfile 额外一层装，不并入 `site/requirements.txt`
   （主体刻意只用标准库 + FastAPI）。有内网 pip 镜像时 `--build-arg PIP_INDEX_URL=` 兜底。
3. **所有硬编码路径参数化**——这是最容易漏的：
   - `bin/make_data.py` / `process_data.py`：`QINGLONG_SOURCE / TARGET / INPUT / OUTPUT / CONCURRENCY / BASE_PATH`，
     不传回退原硬编码值。
   - `QINGLONG_BASE_PATH` **必须传**：qinglong 里 `config/domain.txt` 等资源以它定位，默认写死
     `/data1/minisearch/upload/qinglong`。后端 `weibo._pipeline` 现在总是把它设成 qinglong 目录本身。
   - `src/llm.py` 读 `/data1/minisearch/upload/token/c_token_file` —— 改成**惰性读取、缺文件不在 import 期崩溃**
     （物料链路不调 LLM，只是 import 了模块）。
4. **落地验证三连**（容器内）：
   ```bash
   docker exec zhisou python3 -c "import aiohttp,redis.asyncio,pandas,tqdm; print('deps ok')"
   docker exec -w /app/qinglong zhisou python3 -c "import bin.make_data,bin.process_data; print('import ok')"
   # 单 mid 实跑，看真实报错（后台线程的错在数据集 convert_error 字段，不在 docker logs）
   docker exec zhisou bash -c 'cd /app/qinglong && printf "<真实MID>\n" > /tmp/m.txt && \
     QINGLONG_SOURCE=/tmp/m.txt QINGLONG_TARGET=/tmp/o.jsonl QINGLONG_BASE_PATH=/app/qinglong \
     QINGLONG_CONCURRENCY=1 python3 -m bin.make_data 2>&1 | tail -40; cat /tmp/o.jsonl'
   ```
   产出 JSON 有 `mid_content` / `blog_summary` = 通；有 `_error` = 看报错。

## 四、回滚

`pull-update.sh` 每次把当前 `zhisou:latest` 备份为 `zhisou:prev`：
```bash
docker rm -f zhisou && docker tag zhisou:prev zhisou:latest
docker run -d --name zhisou --restart=always -p 8080:8000 \
  -v /data1/zhisou/data:/app/site/backend/data -v /data1/zhisou/reports:/app/site/backend/reports \
  --env-file /data1/zhisou/zhisou.env zhisou:latest
```
