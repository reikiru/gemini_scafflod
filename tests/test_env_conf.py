"""Tests for host-side bridge/env.conf loading and secret isolation."""

import json
import unittest

from test_bridge import BridgeTestCase


class TestEnvConf(BridgeTestCase):
    ALLOWLIST = "env\n"

    def test_env_conf_injected_and_hot_reloaded(self):
        env_conf = self.root / "bridge" / "env.conf"
        env_conf.write_text(
            "\n".join([
                "# comment line",
                "",
                "TEST_SECRET_A=alpha_123",
                'export TEST_SECRET_B="beta 456"',
                "TEST_SECRET_C='gamma_789'",
            ]) + "\n",
            encoding="utf-8",
        )

        res = self.run_gx("env")
        self.assertEqual(res.returncode, 0, msg=res.stderr)
        self.assertIn("TEST_SECRET_A=alpha_123", res.stdout)
        self.assertIn("TEST_SECRET_B=beta 456", res.stdout)
        self.assertIn("TEST_SECRET_C=gamma_789", res.stdout)

        # Hot-reload without restarting daemon
        env_conf.write_text("TEST_SECRET_A=updated_999\n", encoding="utf-8")
        res2 = self.run_gx("env")
        self.assertEqual(res2.returncode, 0, msg=res2.stderr)
        self.assertIn("TEST_SECRET_A=updated_999", res2.stdout)

    def test_ping_does_not_leak_env_conf_secrets(self):
        (self.root / "bridge" / "env.conf").write_text(
            "SUPER_SECRET_TOKEN=do_not_leak_me\n", encoding="utf-8"
        )
        res = self.run_gx("ping", "--json")
        self.assertEqual(res.returncode, 0, msg=res.stderr)
        self.assertNotIn("do_not_leak_me", res.stdout)
        data = json.loads(res.stdout)
        self.assertTrue(data["ok"])


if __name__ == "__main__":
    unittest.main()
