"""Tests for background job management (gx bg / jobs / tail / kill)."""

import json
import time
import unittest

from test_bridge import BridgeTestCase


class TestBackgroundJobs(BridgeTestCase):
    ALLOWLIST = "\n".join([
        "echo|hello",
        "sleep",
    ]) + "\n"

    def test_bg_start_list_and_kill(self):
        start = self.run_gx("bg", "--json", "--", "sleep", "30")
        self.assertEqual(start.returncode, 0, msg=start.stderr)
        info = json.loads(start.stdout)
        job_id = info["job_id"]
        self.assertTrue(job_id)
        self.assertIsInstance(info["pid"], int)

        jobs_res = self.run_gx("jobs", "--json")
        self.assertEqual(jobs_res.returncode, 0, msg=jobs_res.stderr)
        jobs = json.loads(jobs_res.stdout)
        matched = [j for j in jobs if j["job_id"] == job_id]
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["status"], "running")

        kill_res = self.run_gx("kill", job_id)
        self.assertEqual(kill_res.returncode, 0, msg=kill_res.stderr)

        jobs_after = json.loads(self.run_gx("jobs", "--json").stdout)
        matched_after = [j for j in jobs_after if j["job_id"] == job_id]
        self.assertEqual(len(matched_after), 1)
        self.assertIn(matched_after[0]["status"], ("killed", "exited"))

    def test_bg_short_command_captures_output_and_exits(self):
        start = self.run_gx("bg", "--json", "--", "echo", "hello", "bg_output")
        self.assertEqual(start.returncode, 0, msg=start.stderr)
        job_id = json.loads(start.stdout)["job_id"]

        # Wait briefly for job to finish and be reaped
        deadline = time.time() + 5.0
        final_job = None
        while time.time() < deadline:
            jobs = json.loads(self.run_gx("jobs", "--json").stdout)
            matched = [j for j in jobs if j["job_id"] == job_id]
            if matched and matched[0]["status"] == "exited":
                final_job = matched[0]
                break
            time.sleep(0.1)

        self.assertIsNotNone(final_job, "short bg job did not transition to exited")
        self.assertEqual(final_job["exit"], 0)

        tail_res = self.run_gx("tail", job_id, "-n", "10")
        self.assertEqual(tail_res.returncode, 0, msg=tail_res.stderr)
        self.assertIn("hello bg_output", tail_res.stdout)

    def test_bg_respects_allowlist(self):
        res = self.run_gx("bg", "ls", "-la")
        self.assertEqual(res.returncode, 126)
        self.assertIn("被白名单拒绝", res.stderr)

    def test_kill_unknown_job_fails_cleanly(self):
        res = self.run_gx("kill", "no_such_job_123")
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("找不到", res.stderr)


if __name__ == "__main__":
    unittest.main()
