#!/usr/bin/env python3
"""Gemini 手脚架：文件桥守护进程。

在沙盒之外执行真正需要联网或宿主机环境的命令。沙盒里的 gx 只做两件事：
往 var/queue 写一个请求文件，从 var/done 读回结果文件。

设计约束：
  1. 永不经过 shell，argv 直接 exec，避免命令注入。
  2. 只跑 allowlist.conf 里登记过的命令，其余一律拒绝并留痕。
  3. 每条请求都写审计日志 var/log/bridge.log。
  4. 仅允许透传安全的环境变量，拒绝可劫持加载器或解释器的变量。

Python 3.9 兼容（launchd 里用 /usr/bin/python3 拉起）。
"""

import fcntl
import json
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(os.environ.get("GX_ROOT") or Path(__file__).resolve().parent.parent)
VAR = ROOT / "var"
QUEUE = VAR / "queue"
DONE = VAR / "done"
JOBS = VAR / "jobs"
LOGDIR = VAR / "log"
LOG = LOGDIR / "bridge.log"
PIDFILE = VAR / "bridge.pid"
ALLOWLIST = ROOT / "bridge" / "allowlist.conf"
ENV_CONF = ROOT / "bridge" / "env.conf"

POLL_SEC = 0.05
MAX_CAPTURE = 2 * 1024 * 1024
MAX_TIMEOUT = 4 * 3600
KEEP_SEC = 24 * 3600

ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
BLOCKED_ENV_EXACT = {
    "PATH", "HOME", "SHELL", "USER", "LOGNAME", "IFS",
    "ENV", "BASH_ENV", "CDPATH", "GLOBIGNORE", "PROMPT_COMMAND",
    "ZDOTDIR", "NODE_OPTIONS", "PERL5OPT", "RUBYOPT",
}
BLOCKED_ENV_PREFIXES = ("LD_", "DYLD_", "PYTHON", "BASH_FUNC_")

_running = True
_started_at = time.time()
_active_jobs = {}  # job_id -> {"proc": Popen, "log_fh": file, "meta": dict}


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


def validate_env_overrides(raw_env):
    """校验客户端传入的环境变量覆盖，拒绝危险变量。"""
    if raw_env is None:
        return {}, None
    if not isinstance(raw_env, dict):
        return None, "env 字段必须为对象"
    clean = {}
    for k, v in raw_env.items():
        if not isinstance(k, str) or not isinstance(v, str) or not ENV_KEY_RE.match(k):
            return None, "非法环境变量名或值: %r" % (k,)
        upper = k.upper()
        if upper in BLOCKED_ENV_EXACT or any(upper.startswith(p) for p in BLOCKED_ENV_PREFIXES):
            return None, "环境变量 %s 被安全策略拒绝" % k
        clean[k] = v
    return clean, None


def load_host_env():
    """从本机私有 bridge/env.conf 加载宿主机环境变量（热加载，不入库）。"""
    loaded = {}
    if not ENV_CONF.exists():
        return loaded
    try:
        for raw in ENV_CONF.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:].strip()
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
                v = v[1:-1]
            if ENV_KEY_RE.match(k):
                loaded[k] = v
    except Exception as e:
        log("WARN 读取 env.conf 失败: %r" % (e,))
    return loaded


def build_exec_env(env_overrides):
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.setdefault("LANG", "en_US.UTF-8")
    env.setdefault("LC_ALL", "en_US.UTF-8")
    env.update(load_host_env())
    env.update(env_overrides)
    return env


def resolve_cwd(raw_cwd):
    cwd = raw_cwd or str(Path.home())
    if not os.path.isdir(cwd):
        cwd = str(Path.home())
    return cwd


def reap_jobs():
    for job_id, entry in list(_active_jobs.items()):
        proc = entry["proc"]
        rc = proc.poll()
        if rc is None:
            continue
        try:
            entry["log_fh"].close()
        except Exception:
            pass
        meta = entry["meta"]
        if meta.get("status") == "running":
            meta["status"] = "exited"
        meta["exit"] = rc
        meta["finished_at"] = round(time.time(), 2)
        write_json_atomic(JOBS / (job_id + ".json"), meta)
        _active_jobs.pop(job_id, None)
        log("BG_EXIT %s exit=%s %s" % (job_id, rc, json.dumps(meta.get("argv", []), ensure_ascii=False)))


def terminate_process_group(proc, wait_sec=2.0):
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except Exception:
        try:
            proc.terminate()
        except Exception:
            pass
    try:
        proc.wait(timeout=wait_sec)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        try:
            proc.wait(timeout=2.0)
        except Exception:
            pass


def handle_ping(req_id):
    reap_jobs()
    resp = {
        "id": req_id,
        "exit": 0,
        "ok": True,
        "pid": os.getpid(),
        "uptime_sec": round(time.time() - _started_at, 2),
        "home": str(Path.home()),
        "path": os.environ.get("PATH", ""),
        "rules_count": len(load_rules()),
        "active_jobs": len(_active_jobs),
    }
    write_json_atomic(DONE / (req_id + ".json"), resp)


def handle_jobs(req_id):
    reap_jobs()
    items = []
    now_ts = time.time()
    if JOBS.is_dir():
        for p in sorted(JOBS.glob("*.json"), reverse=True):
            try:
                meta = json.loads(p.read_text(encoding="utf-8"))
                end_ts = meta.get("finished_at") or now_ts
                meta["elapsed_sec"] = round(max(0.0, end_ts - meta.get("started_at", now_ts)), 2)
                items.append(meta)
            except Exception:
                pass
    write_json_atomic(DONE / (req_id + ".json"), {"id": req_id, "exit": 0, "jobs": items})


def handle_kill_job(req_id, req):
    reap_jobs()
    job_id = str(req.get("job_id") or "").strip()
    if not job_id or "/" in job_id or ".." in job_id:
        write_json_atomic(DONE / (req_id + ".json"), {"id": req_id, "exit": 2, "error": "非法 job_id"})
        return

    meta_path = JOBS / (job_id + ".json")
    entry = _active_jobs.get(job_id)
    if entry is not None:
        proc = entry["proc"]
        terminate_process_group(proc)
        try:
            entry["log_fh"].close()
        except Exception:
            pass
        meta = entry["meta"]
        meta["status"] = "killed"
        meta["exit"] = proc.returncode
        meta["finished_at"] = round(time.time(), 2)
        write_json_atomic(meta_path, meta)
        _active_jobs.pop(job_id, None)
        log("BG_KILL %s pid=%s" % (job_id, meta.get("pid")))
        write_json_atomic(DONE / (req_id + ".json"), {
            "id": req_id, "exit": 0, "job_id": job_id, "status": "killed",
        })
        return

    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            meta = {"status": "unknown"}
        write_json_atomic(DONE / (req_id + ".json"), {
            "id": req_id, "exit": 0, "job_id": job_id,
            "status": meta.get("status", "exited"), "note": "任务已结束",
        })
        return

    write_json_atomic(DONE / (req_id + ".json"), {
        "id": req_id, "exit": 1, "error": "找不到后台任务: %s" % job_id,
    })


def handle_bg(req_id, req, argv, env_overrides):
    JOBS.mkdir(parents=True, exist_ok=True)
    job_id = req_id
    log_path = JOBS / (job_id + ".log")
    cwd = resolve_cwd(req.get("cwd"))
    env = build_exec_env(env_overrides)

    try:
        log_fh = log_path.open("ab")
        proc = subprocess.Popen(
            argv,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    except FileNotFoundError:
        log("FAIL %s %s  (找不到可执行文件)" % (req_id, json.dumps(argv, ensure_ascii=False)))
        write_json_atomic(DONE / (req_id + ".json"),
                          {"id": req_id, "exit": 127, "error": "找不到可执行文件: %s" % argv[0]})
        return
    except Exception as e:
        write_json_atomic(DONE / (req_id + ".json"),
                          {"id": req_id, "exit": 98, "error": "后台启动失败: %s" % e})
        return

    meta = {
        "job_id": job_id,
        "pid": proc.pid,
        "argv": argv,
        "cwd": cwd,
        "started_at": round(time.time(), 2),
        "finished_at": None,
        "status": "running",
        "exit": None,
        "log_file": str(log_path),
    }
    write_json_atomic(JOBS / (job_id + ".json"), meta)
    _active_jobs[job_id] = {"proc": proc, "log_fh": log_fh, "meta": meta}
    log("BG_START %s pid=%s %s" % (job_id, proc.pid, json.dumps(argv, ensure_ascii=False)))
    write_json_atomic(DONE / (req_id + ".json"), {
        "id": req_id,
        "exit": 0,
        "job_id": job_id,
        "pid": proc.pid,
        "log_file": str(log_path),
    })


def handle(req_path):
    req_id = req_path.stem
    try:
        req = json.loads(req_path.read_text(encoding="utf-8"))
    except Exception as e:
        write_json_atomic(DONE / (req_id + ".json"),
                          {"id": req_id, "exit": 99, "error": "请求文件解析失败: %s" % e})
        req_path.unlink(missing_ok=True)
        return

    action = req.get("action") or "exec"
    if action == "ping":
        handle_ping(req_id)
        req_path.unlink(missing_ok=True)
        return
    if action == "jobs":
        handle_jobs(req_id)
        req_path.unlink(missing_ok=True)
        return
    if action == "kill_job":
        handle_kill_job(req_id, req)
        req_path.unlink(missing_ok=True)
        return

    argv = req.get("argv") or []
    if not isinstance(argv, list) or not argv or not all(isinstance(a, str) for a in argv):
        write_json_atomic(DONE / (req_id + ".json"),
                          {"id": req_id, "exit": 99, "error": "argv 非法"})
        req_path.unlink(missing_ok=True)
        return

    env_overrides, env_err = validate_env_overrides(req.get("env"))
    if env_err:
        log("DENY %s env (%s)" % (req_id, env_err))
        write_json_atomic(DONE / (req_id + ".json"),
                          {"id": req_id, "exit": 126, "denied": True, "error": env_err})
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

    if action == "bg":
        handle_bg(req_id, req, argv, env_overrides)
        req_path.unlink(missing_ok=True)
        return

    cwd = resolve_cwd(req.get("cwd"))
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
    env = build_exec_env(env_overrides)

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
    if JOBS.is_dir():
        for p in JOBS.iterdir():
            try:
                if p.stem in _active_jobs:
                    continue
                if p.stat().st_mtime < cutoff:
                    p.unlink()
            except Exception:
                pass


def main():
    global _started_at
    _started_at = time.time()

    for d in (QUEUE, DONE, JOBS, LOGDIR):
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
            reap_jobs()
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

    for job_id, entry in list(_active_jobs.items()):
        terminate_process_group(entry["proc"], wait_sec=1.0)
        try:
            entry["log_fh"].close()
        except Exception:
            pass
    _active_jobs.clear()

    log("=== bridge 退出 pid=%d" % os.getpid())
    return 0


if __name__ == "__main__":
    sys.exit(main())
