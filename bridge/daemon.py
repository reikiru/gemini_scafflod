#!/usr/bin/env python3
"""Gemini 手脚架：文件桥守护进程。

在沙盒之外执行真正需要联网的命令。沙盒里的 gx 只做两件事：
往 var/queue 写一个请求文件，从 var/done 读回结果文件。

设计约束：
  1. 永不经过 shell，argv 直接 exec，避免命令注入。
  2. 只跑 allowlist.conf 里登记过的命令，其余一律拒绝并留痕。
  3. 每条请求都写审计日志 var/log/bridge.log。

Python 3.9 兼容（launchd 里用 /usr/bin/python3 拉起）。
"""

import fcntl
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VAR = ROOT / "var"
QUEUE = VAR / "queue"
DONE = VAR / "done"
LOGDIR = VAR / "log"
LOG = LOGDIR / "bridge.log"
PIDFILE = VAR / "bridge.pid"
ALLOWLIST = ROOT / "bridge" / "allowlist.conf"

POLL_SEC = 0.05
MAX_CAPTURE = 2 * 1024 * 1024
MAX_TIMEOUT = 4 * 3600
KEEP_SEC = 24 * 3600

_running = True


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(msg):
    try:
        LOGDIR.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write("%s\t%s\n" % (now(), msg))
    except Exception:
        pass


def write_json_atomic(path, obj):
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def load_rules():
    """每行一条：可执行名，或 `可执行名|必须的前缀参数`。空行与 # 开头忽略。"""
    rules = []
    if not ALLOWLIST.exists():
        return rules
    for raw in ALLOWLIST.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "|" in line:
            head, rest = line.split("|", 1)
            rules.append((head.strip(), [p for p in rest.split("|") if p]))
        else:
            rules.append((line, []))
    return rules


def check_allowed(argv, rules):
    binary = os.path.basename(argv[0])
    for name, prefix in rules:
        if os.path.basename(name) != binary:
            continue
        if not prefix:
            return True, ""
        if len(argv) >= 1 + len(prefix) and argv[1:1 + len(prefix)] == prefix:
            return True, ""
    return False, "%s 不在白名单内，或前缀参数不匹配" % binary


def handle(req_path):
    req_id = req_path.stem
    try:
        req = json.loads(req_path.read_text(encoding="utf-8"))
    except Exception as e:
        write_json_atomic(DONE / (req_id + ".json"),
                          {"id": req_id, "exit": 99, "error": "请求文件解析失败: %s" % e})
        req_path.unlink(missing_ok=True)
        return

    argv = req.get("argv") or []
    if not isinstance(argv, list) or not argv or not all(isinstance(a, str) for a in argv):
        write_json_atomic(DONE / (req_id + ".json"),
                          {"id": req_id, "exit": 99, "error": "argv 非法"})
        req_path.unlink(missing_ok=True)
        return

    rules = load_rules()
    ok, why = check_allowed(argv, rules)
    if not ok:
        log("DENY %s %s  (%s)" % (req_id, json.dumps(argv, ensure_ascii=False), why))
        write_json_atomic(DONE / (req_id + ".json"),
                          {"id": req_id, "exit": 126, "denied": True, "error": why})
        req_path.unlink(missing_ok=True)
        return

    cwd = req.get("cwd") or str(Path.home())
    if not os.path.isdir(cwd):
        cwd = str(Path.home())

    try:
        timeout = float(req.get("timeout") or 120)
    except Exception:
        timeout = 120.0
    timeout = min(max(timeout, 1.0), MAX_TIMEOUT)

    stdin_data = req.get("stdin")
    if stdin_data is not None:
        stdin_data = str(stdin_data).encode("utf-8")

    out_file = req.get("stdout_file")
    started = time.time()
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)

    try:
        proc = subprocess.Popen(
            argv,
            cwd=cwd,
            env=env,
            stdin=subprocess.PIPE if stdin_data is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
    except FileNotFoundError:
        log("FAIL %s %s  (找不到可执行文件)" % (req_id, json.dumps(argv, ensure_ascii=False)))
        write_json_atomic(DONE / (req_id + ".json"),
                          {"id": req_id, "exit": 127, "error": "找不到可执行文件: %s" % argv[0]})
        req_path.unlink(missing_ok=True)
        return
    except Exception as e:
        write_json_atomic(DONE / (req_id + ".json"),
                          {"id": req_id, "exit": 98, "error": "启动失败: %s" % e})
        req_path.unlink(missing_ok=True)
        return

    timed_out = False
    try:
        out, err = proc.communicate(input=stdin_data, timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception:
            proc.kill()
        out, err = proc.communicate()

    elapsed = int((time.time() - started) * 1000)
    resp = {
        "id": req_id,
        "exit": proc.returncode,
        "duration_ms": elapsed,
        "timed_out": timed_out,
    }

    if out_file:
        try:
            target = Path(os.path.expanduser(out_file))
            if not target.is_absolute():
                target = Path(cwd) / target
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(out)
            resp["stdout_file"] = str(target)
            resp["bytes"] = len(out)
        except Exception as e:
            resp["error"] = "写文件失败: %s" % e
    else:
        text = out.decode("utf-8", "replace")
        if len(text) > MAX_CAPTURE:
            text = text[:MAX_CAPTURE] + "\n[输出超过 2MB，已截断]"
        resp["stdout"] = text

    err_text = err.decode("utf-8", "replace")
    if err_text:
        resp["stderr"] = err_text[:MAX_CAPTURE]

    write_json_atomic(DONE / (req_id + ".json"), resp)
    req_path.unlink(missing_ok=True)
    log("RUN %s exit=%s %sms %s%s" % (
        req_id, proc.returncode, elapsed,
        json.dumps(argv, ensure_ascii=False),
        " (超时)" if timed_out else ""))


def sweep():
    cutoff = time.time() - KEEP_SEC
    for d in (QUEUE, DONE):
        if not d.is_dir():
            continue
        for p in d.iterdir():
            try:
                if p.stat().st_mtime < cutoff:
                    p.unlink()
            except Exception:
                pass


def main():
    for d in (QUEUE, DONE, LOGDIR):
        d.mkdir(parents=True, exist_ok=True)

    lock = PIDFILE.open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("已在运行，退出", file=sys.stderr)
        return 0
    lock.write(str(os.getpid()))
    lock.flush()

    def stop(_signum, _frame):
        global _running
        _running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    log("=== bridge 启动 pid=%d root=%s" % (os.getpid(), ROOT))
    last_sweep = 0.0
    while _running:
        try:
            pending = sorted(QUEUE.glob("*.json"))
            if pending:
                for p in pending:
                    if not _running:
                        break
                    try:
                        handle(p)
                    except Exception as e:
                        log("ERR 处理 %s 失败: %r" % (p.name, e))
            else:
                time.sleep(POLL_SEC)
            if time.time() - last_sweep > 600:
                sweep()
                last_sweep = time.time()
        except Exception as e:
            log("ERR 主循环: %r" % e)
            time.sleep(1)

    log("=== bridge 退出 pid=%d" % os.getpid())
    return 0


if __name__ == "__main__":
    sys.exit(main())
