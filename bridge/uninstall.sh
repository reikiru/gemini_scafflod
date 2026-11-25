#!/bin/bash
# 卸载文件桥：停掉并移除 launchd 服务。var/ 里的日志保留。
set -euo pipefail

LABEL="${GX_LABEL:-com.gemini.bridge}"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

launchctl bootout "gui/$UID/$LABEL" >/dev/null 2>&1 || true
rm -f "$PLIST"
echo "已卸载：$LABEL"
