#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
WEBSITE_DIR="$SCRIPT_DIR/webside"
CONDA_ENV_NAME="webFaceEmotionRec"

BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  if [[ -n "${FRONTEND_PID}" ]] && kill -0 "${FRONTEND_PID}" 2>/dev/null; then
    kill "${FRONTEND_PID}" 2>/dev/null || true
  fi

  if [[ -n "${BACKEND_PID}" ]] && kill -0 "${BACKEND_PID}" 2>/dev/null; then
    kill "${BACKEND_PID}" 2>/dev/null || true
  fi
}

trap cleanup EXIT INT TERM

if ! command -v conda >/dev/null 2>&1; then
  if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
    # Miniconda 常见安装路径
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
  elif [[ -f "$HOME/anaconda3/etc/profile.d/conda.sh" ]]; then
    # Anaconda 常见安装路径
    source "$HOME/anaconda3/etc/profile.d/conda.sh"
  else
    echo "未找到 conda，请先安装并确保可以使用环境: ${CONDA_ENV_NAME}"
    exit 1
  fi
else
  CONDA_BASE="$(conda info --base)"
  source "${CONDA_BASE}/etc/profile.d/conda.sh"
fi

conda activate "${CONDA_ENV_NAME}"

echo "启动后端服务..."
cd "$BACKEND_DIR"
python main.py &
BACKEND_PID=$!

if [[ -f "$WEBSITE_DIR/package.json" ]]; then
  echo "启动前端服务..."
  cd "$WEBSITE_DIR"

  if [[ ! -d "$WEBSITE_DIR/node_modules" ]]; then
    echo "检测到前端依赖未安装，正在执行 npm install..."
    npm install
  fi

  npm run dev &
  FRONTEND_PID=$!
fi

cd "$SCRIPT_DIR"
echo "服务已启动。按 Ctrl+C 可停止后端和前端。"

wait
