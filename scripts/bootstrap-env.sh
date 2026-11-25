#!/usr/bin/env bash
# 从当前登录 shell 环境或 ~/.zshenv 同步常见搜索 API Key 到本机私有 bridge/env.conf（权限 600，不入库）。
# 用法：bash scripts/bootstrap-env.sh [KEY1 KEY2 ...]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/bridge/env.conf"
KEYS=("$@")
if [ "${#KEYS[@]}" -eq 0 ]; then
  KEYS=(TAVILY_API_KEY EXA_API_KEY FIRECRAWL_API_KEY)
fi

read_key_from_shell_files() {
  local key="$1"
  local val="${!key:-}"
  if [ -n "$val" ]; then
    printf '%s' "$val"
    return 0
  fi
  local file line
  for file in "$HOME/.zshenv" "$HOME/.zshrc" "$HOME/.zprofile" "$HOME/.bashrc"; do
    [ -f "$file" ] || continue
    line="$(grep -E "^[[:space:]]*(export[[:space:]]+)?${key}=" "$file" | tail -n 1 || true)"
    if [ -n "$line" ]; then
      val="${line#*=}"
      val="${val#\"}"
      val="${val%\"}"
      val="${val#\'}"
      val="${val%\'}"
      printf '%s' "$val"
      return 0
    fi
  done
  return 1
}

mkdir -p "$(dirname "$OUT")"
tmp="$(mktemp)"
chmod 600 "$tmp"

{
  echo "# 由 scripts/bootstrap-env.sh 生成（本机私有，不纳入版本控制）"
  for key in "${KEYS[@]}"; do
    if val="$(read_key_from_shell_files "$key")" && [ -n "$val" ]; then
      printf '%s=%s\n' "$key" "$val"
      echo "已同步变量名: $key" >&2
    else
      echo "# $key="
      echo "未找到变量: $key（已留空注释）" >&2
    fi
  done
} > "$tmp"

mv "$tmp" "$OUT"
chmod 600 "$OUT"
echo "已写入 $OUT（权限 600）" >&2
