"""Unit and end-to-end tests for the file-queue bridge (daemon.py + gx)."""

import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DAEMON_SCRIPT = REPO_ROOT / "bridge" / "daemon.py"
GX_SCRIPT = REPO_ROOT / "bridge" / "gx"


class BridgeTestCase(unittest.TestCase):
    """Spins up an isolated daemon.py backed by a temporary GX_ROOT."""

    ALLOWLIST = "\n".join([
        "echo|hello",
        "cat",
        "sleep",
        "printf",
    ]) + "\n"

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory(prefix="gx_test_")
        self.root = Path(self.tmpdir.name)
        (self.root / "bridge").mkdir(parents=True)
        (self.root / "var").mkdir(parents=True)
        (self.root / "bridge" / "allowlist.conf").write_text(self.ALLOWLIST, encoding="utf-8")

        self.env = os.environ.copy()
        self.env["GX_ROOT"] = str(self.root)

        self.daemon = subprocess.Popen(
            [sys.executable, str(DAEMON_SCRIPT)],
            env=self.env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        # Wait for bridge.pid to appear
        pidfile = self.root / "var" / "bridge.pid"
        deadline = time.time() + 5.0
        while time.time() < deadline:
            if pidfile.exists() and pidfile.read_text().strip():
                break
            time.sleep(0.05)
        else:
            self.fail("daemon.py failed to start and write bridge.pid")

    def tearDown(self):
        if self.daemon.poll() is None:
            self.daemon.terminate()
            try:
                self.daemon.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.daemon.kill()
                self.daemon.wait()
        self.tmpdir.cleanup()

    def run_gx(self, *args, stdin_text=None):
        return subprocess.run(
            [sys.executable, str(GX_SCRIPT), *args],
            env=self.env,
            input=stdin_text,
            capture_output=True,
            text=True,
            timeout=15,
        )


class TestBridgeSync(BridgeTestCase):
    def test_allowlisted_prefix_allowed_and_mismatch_denied(self):
        ok = self.run_gx("echo", "hello", "world")
        self.assertEqual(ok.returncode, 0)
        self.assertEqual(ok.stdout.strip(), "hello world")

        denied = self.run_gx("echo", "other")
        self.assertEqual(denied.returncode, 126)
        self.assertIn("被白名单拒绝", denied.stderr)

    def test_unlisted_command_denied_and_logged(self):
        res = self.run_gx("ls", "-la")
        self.assertEqual(res.returncode, 126)
        log_text = (self.root / "var" / "log" / "bridge.log").read_text(encoding="utf-8")
        self.assertIn("DENY", log_text)
        self.assertIn('"ls"', log_text)

    def test_stdin_passthrough(self):
        res = self.run_gx("cat", stdin_text="line1\nline2\n")
        self.assertEqual(res.returncode, 0)
        self.assertEqual(res.stdout, "line1\nline2\n")

    def test_stdout_file_writes_raw_bytes(self):
        out_path = self.root / "var" / "out.bin"
        res = self.run_gx("--stdout-file", str(out_path), "--", "printf", "ABC123")
        self.assertEqual(res.returncode, 0)
        self.assertTrue(out_path.exists())
        self.assertEqual(out_path.read_bytes(), b"ABC123")

    def test_timeout_kills_command(self):
        res = self.run_gx("--timeout", "1", "--", "sleep", "10")
        self.assertEqual(res.returncode, 124)
        self.assertIn("超时", res.stderr)

    def test_status_reports_running(self):
        res = self.run_gx("status")
        self.assertEqual(res.returncode, 0)
        self.assertIn("在跑", res.stdout)


if __name__ == "__main__":
    unittest.main()
