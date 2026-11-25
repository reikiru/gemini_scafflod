"""Static and behavior checks for bridge/install.sh."""

import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INSTALL_SH = REPO_ROOT / "bridge" / "install.sh"


class TestInstallScript(unittest.TestCase):
    def test_bash_syntax_valid(self):
        res = subprocess.run(["bash", "-n", str(INSTALL_SH)], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, msg=res.stderr)

    def test_guards_against_sudo_and_waits_for_bootout(self):
        text = INSTALL_SH.read_text(encoding="utf-8")
        self.assertIn("EUID", text, "install.sh should guard against running as root/sudo")
        self.assertIn("launchctl enable", text, "install.sh should ensure service is enabled before bootstrap")
        self.assertIn("sleep 0.2", text, "install.sh should wait for bootout to finish before bootstrap")


if __name__ == "__main__":
    unittest.main()
