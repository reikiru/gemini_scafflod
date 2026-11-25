# gemini_scaffold

给 Gemini 桌面应用搭的通用脚手架，聚焦两件事：
1. 集中维护给 Gemini 使用的 `AGENTS.md` 协作规范。
2. 提供沙盒外文件桥等工具，补齐 Gemini 客户端在联网、本地端口访问、进程观测、真实用户环境等方面的能力限制。

## 目录结构

```text
gemini_scaffold/
├── README.md                    项目总入口
├── AGENTS.md                    Gemini 协作规范（自行编写）
├── 用法.md                      文件桥安装、命令清单与安全边界
├── .gitignore
├── bridge/
│   ├── gx                       沙盒内通用客户端（只读写文件）
│   ├── daemon.py                沙盒外常驻守护进程（按白名单 exec）
│   ├── allowlist.conf.example   白名单模板（本机复制为 allowlist.conf）
│   ├── install.sh               注册 launchd 服务
│   └── uninstall.sh             卸载 launchd 服务
└── var/                         本机运行时数据：queue、done、log（不入库）
```

## 环境与依赖

| 项 | 要求 | 说明 |
|---|---|---|
| macOS | 支持 `launchd` 用户级服务 | 也可前台直接运行 `bridge/daemon.py` |
| Python | 3.9 及以上 | 守护进程默认使用 `/usr/bin/python3` |
| 被桥接命令 | 视本机白名单而定 | 可通过环境变量 `GX_PATH` 自定义 `PATH` |

## 设计要点

- **免弹窗穿透**：客户端不建立任何网络连接或 UNIX Socket，只读写 `var/` 下的队列文件，不触发 Gemini 的网络批准弹窗。
- **防注入执行**：守护进程直接 `exec`，不经过 shell，参数不会被 shell 解释。
- **最小权限白名单**：`bridge/allowlist.conf`（本机私有，不入库）按可执行名匹配，可用 `|` 锁死参数前缀；严禁放行通用解释器。
- **全程留痕**：每条请求记录耗时、退出码与完整 `argv` 到 `var/log/bridge.log`。

详细安装与用法见 [用法.md](用法.md)。
