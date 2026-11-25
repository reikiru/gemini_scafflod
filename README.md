# gemini_scaffold

给 Gemini 桌面应用搭的通用脚手架，聚焦两件事：
1. 集中维护给 Gemini 使用的 `AGENTS.md` 协作规范（仓库提供脱敏模板 `AGENTS.md.example`）。
2. 提供沙盒外文件桥等工具，补齐 Gemini 客户端在联网、本地端口、进程观测、环境变量、凭据与后台长任务上的限制。

## 目录结构

```text
gemini_scaffold/
├── README.md                    项目总入口
├── AGENTS.md                    Gemini 协作规范（自用，可参考 AGENTS.md.example）
├── AGENTS.md.example            脱敏后的协作规范模板
├── 用法.md                      安装、命令清单、沙盒限制说明与安全边界
├── .gitignore
├── bridge/
│   ├── gx                       沙盒内通用客户端（同步、后台作业、探活、日志）
│   ├── daemon.py                沙盒外常驻守护进程（白名单 exec + 后台作业池 + env.conf 热加载）
│   ├── allowlist.conf.example   白名单模板（本机复制为 allowlist.conf）
│   ├── env.conf.example         宿主机密钥模板（本机复制为 env.conf，不入库）
│   ├── install.sh               注册 launchd 服务
│   └── uninstall.sh             卸载 launchd 服务
├── tools/
│   └── web-search               零依赖 Tavily / Exa 联网搜索 CLI
├── scripts/
│   └── bootstrap-env.sh         从本机 shell 配置同步搜索 API Key 到 bridge/env.conf
├── skills/                      设备解耦的 Gemini Skill 模板（agent-browser / firecrawl / web-search-api）
├── tests/                       零依赖 unittest 自动化测试套件
└── var/                         本机运行时数据：queue、done、jobs、log（不入库）
```

## 环境与依赖

| 项 | 要求 | 说明 |
|---|---|---|
| macOS | 支持 `launchd` 用户级服务 | 也可前台直接运行 `bridge/daemon.py` |
| Python | 3.9 及以上 | 守护进程与测试均零第三方依赖 |
| 被桥接命令 | 视本机白名单而定 | 可通过环境变量 `GX_PATH` 自定义 `PATH` |

## 核心能力与设计要点

- **免弹窗穿透**：客户端不建立任何网络连接或 UNIX Socket，只读写 `var/` 下的队列文件，不触发 Gemini 的网络批准弹窗。
- **防注入执行**：守护进程直接 `exec`，不经过 shell，参数不会被 shell 解释。
- **最小权限白名单 + 环境变量防护**：`bridge/allowlist.conf`（本机私有，不入库）按可执行名及前缀参数放行；`--env` 强制拒绝 `PATH`/`LD_*`/`DYLD_*`/`PYTHON*` 等危险变量。
- **异步后台作业与端到端探活**：支持 `gx bg`/`jobs`/`tail`/`kill` 管理后台长任务，支持 `gx ping` 探测宿主机真实 `HOME`/`PATH` 与守护进程状态。

详细安装、命令清单与测试方式见 [用法.md](用法.md)。
