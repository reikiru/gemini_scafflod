"""Validation tests for repo-bundled device-agnostic skills under skills/."""

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / "skills"
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FORBIDDEN_PATTERNS = ("/Users/", "tvly-", "fc-", "—", "–")


def parse_frontmatter(text):
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    meta = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return meta
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return None


class TestSkillsLayout(unittest.TestCase):
    def test_all_skills_valid_and_device_agnostic(self):
        self.assertTrue(SKILLS_DIR.is_dir(), "skills/ directory must exist")
        skill_dirs = sorted(p for p in SKILLS_DIR.iterdir() if p.is_dir())
        self.assertGreaterEqual(len(skill_dirs), 4)

        for d in skill_dirs:
            skill_md = d / "SKILL.md"
            self.assertTrue(skill_md.is_file(), f"missing SKILL.md in {d.name}")
            content = skill_md.read_text(encoding="utf-8")
            meta = parse_frontmatter(content)
            self.assertIsNotNone(meta, f"invalid YAML frontmatter in {d.name}")

            name = meta.get("name", "")
            desc = meta.get("description", "")
            self.assertEqual(name, d.name, f"frontmatter name must match dir {d.name}")
            self.assertRegex(name, NAME_RE)
            self.assertLessEqual(len(name), 64)
            self.assertTrue(10 <= len(desc) <= 1024, f"invalid description length in {d.name}")

            for pat in FORBIDDEN_PATTERNS:
                self.assertNotIn(pat, content, f"forbidden pattern {pat!r} found in {d.name}/SKILL.md")


if __name__ == "__main__":
    unittest.main()
