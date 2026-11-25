#!/bin/bash
# 安装文件桥：注册 launchd 用户级守护进程。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="${GX_LABEL:-com.gemini.bridge}"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
DEFAULT_PATH="$ROOT/tools:/opt/homebrew/bin:$HOME/.homebrew/bin:$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
BRIDGE_PATH="${GX_PATH:-$DEFAULT_PATH}"

mkdir -p "$ROOT/var/queue" "$ROOT/var/done" "$ROOT/var/log"
chmod 700 "$ROOT/var"
chmod +x "$ROOT/bridge/gx" "$ROOT/bridge/daemon.py"

if [ ! -f "$ROOT/bridge/allowlist.conf" ] && [ -f "$ROOT/bridge/allowlist.conf.example" ]; then
  cp "$ROOT/bridge/allowlist.conf.example" "$ROOT/bridge/allowlist.conf"
  echo "已从模板生成白名单：$ROOT/bridge/allowlist.conf"
fi

if [ ! -f "$ROOT/bridge/env.conf" ] && [ -f "$ROOT/bridge/env.conf.example" ]; then
  cp "$ROOT/bridge/env.conf.example" "$ROOT/bridge/env.conf"
  chmod 600 "$ROOT/bridge/env.conf"
  echo "已从模板生成环境变量文件：$ROOT/bridge/env.conf"
fi

cat > "$PLIST" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>$ROOT/bridge/daemon.py</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>$BRIDGE_PATH</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ProcessType</key><string>Background</string>
  <key>StandardOutPath</key><string>$ROOT/var/log/launchd.out.log</string>
  <key>StandardErrorPath</key><string>$ROOT/var/log/launchd.err.log</string>
</dict>
</plist>
PLIST_EOF

launchctl bootout "gui/$UID/$LABEL" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$UID" "$PLIST"
sleep 1

if launchctl print "gui/$UID/$LABEL" 2>/dev/null | grep -q "state = running"; then
  echo "守护进程已启动：$LABEL"
else
  echo "启动失败，看 $ROOT/var/log/launchd.err.log" >&2
  exit 1
fi

echo "plist: $PLIST"
echo "自检：$ROOT/bridge/gx status"
