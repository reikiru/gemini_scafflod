"""Tests for gx ping healthcheck and safe --env passthrough."""

import json
import unittest

from test_bridge import BridgeTestCase


class TestHealthAndEnv(BridgeTestCase):
    ALLOWLIST = "env\n"

    def test_ping_human_readable(self):
        res = self.run_gx("ping")
        self.assertEqual(res.returncode, 0, msg=res.stderr)
        self.assertIn("pong", res.stdout.lower())
        self.assertIn("pid=", res.stdout)
        self.assertIn("rules=1", res.stdout)

    def test_ping_json(self):
        res = self.run_gx("ping", "--json")
        self.assertEqual(res.returncode, 0, msg=res.stderr)
        data = json.loads(res.stdout)
        self.assertTrue(data["ok"])
        self.assertEqual(data["pid"], self.daemon.pid)
        self.assertEqual(data["rules_count"], 1)
        self.assertIn("home", data)
        self.assertIn("path", data)
        self.assertGreaterEqual(data["uptime_sec"], 0)

    def test_safe_env_passthrough(self):
        res = self.run_gx("--env", "MY_TEST_KEY=hello_42", "-e", "SECOND_KEY=ok", "--", "env")
        self.assertEqual(res.returncode, 0, msg=res.stderr)
        self.assertIn("MY_TEST_KEY=hello_42", res.stdout)
        self.assertIn("SECOND_KEY=ok", res.stdout)

    def test_dangerous_env_vars_rejected(self):
        for bad in (
            "PATH=/tmp/evil",
            "DYLD_INSERT_LIBRARIES=/tmp/evil.dylib",
            "LD_PRELOAD=/tmp/evil.so",
            "PYTHONPATH=/tmp/evil",
            "BASH_ENV=/tmp/evil.sh",
        ):
            res = self.run_gx("--env", bad, "--", "env")
            self.assertNotEqual(res.returncode, 0, msg=f"should reject {bad}")
            self.assertIn("拒绝", res.stderr)

    def test_invalid_env_format_rejected(self):
        res = self.run_gx("--env", "NO_EQUALS_SIGN", "--", "env")
        self.assertEqual(res.returncode, 2)


if __name__ == "__main__":
    unittest.main()
