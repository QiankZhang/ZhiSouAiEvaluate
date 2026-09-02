#!/usr/bin/env bash
###############################################################################
# 打发布包 —— 在【有外网 + 有 Node>=22.13】的机器上执行（开发机 / CI）
#
#   bash site/deploy/make-release.sh
#
# 产出 dist/zhisou-release-<日期>.tar.gz，内含：
#   - 全部源码
#   - 已构建的前端 site/frontend/dist
#   - 离线 Python 依赖 wheels（site/deploy/vendor/wheels）
# 把这个 tar 包拷到内网服务器，解压后执行 deploy/install.sh 即可，全程无需外网。
###############################################################################
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO"

command -v npm  >/dev/null || { echo "需要 Node/npm(>=22.13)"; exit 1; }
command -v pip3 >/dev/null || command -v pip >/dev/null || { echo "需要 pip"; exit 1; }
PIP="$(command -v pip3 || command -v pip)"

STAMP="$(date +%Y%m%d)"
STAGE="$(mktemp -d)/zhisou"
OUT="$REPO/dist/zhisou-release-$STAMP.tar.gz"
mkdir -p "$REPO/dist"

echo "==> 构建前端"
npm --prefix site/frontend ci  || npm --prefix site/frontend install
npm --prefix site/frontend run build

echo "==> 下载离线 Python wheels（目标：linux x86_64 / CPython 3.11）"
# 目标服务器多为 x86_64 + python3.11。绝大多数依赖是纯 Python，只有 pydantic-core 是平台相关轮子，
# 因此显式指定平台，避免在 macOS/arm 打包机上抓到不匹配的轮子。
# 目标机器是 ARM 或其它 Python 版本时，改下面两个参数，或直接在一台同架构 Linux 上执行本脚本。
TARGET_PY="${TARGET_PY:-3.11}"
TARGET_PLATFORM="${TARGET_PLATFORM:-manylinux2014_x86_64}"
rm -rf site/deploy/vendor/wheels
mkdir -p site/deploy/vendor/wheels
"$PIP" download -d site/deploy/vendor/wheels -r site/requirements.txt \
  --only-binary=:all: --python-version "$TARGET_PY" --platform "$TARGET_PLATFORM" \
  || "$PIP" download -d site/deploy/vendor/wheels -r site/requirements.txt   # 退化：本机平台

echo "==> 组装发布包"
mkdir -p "$STAGE"
rsync -a \
  --exclude='.git/' \
  --exclude='node_modules/' \
  --exclude='**/__pycache__/' \
  --exclude='.venv/' \
  --exclude='dist/zhisou-release-*.tar.gz' \
  --exclude='site/backend/.env' \
  --exclude='site/backend/data/' \
  --exclude='site/backend/reports/' \
  ./ "$STAGE"/
# site/frontend/dist 与 site/deploy/vendor/wheels 被 .gitignore 忽略，rsync 默认仍会带上（不是 --filter=:C）

tar czf "$OUT" -C "$(dirname "$STAGE")" zhisou
rm -rf "$(dirname "$STAGE")"

echo "==> 完成: $OUT ($(du -h "$OUT" | cut -f1))"
echo "   拷到服务器后: tar xzf $(basename "$OUT") && sudo bash zhisou/site/deploy/install.sh"
