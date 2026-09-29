import os
import re
import unittest

from helpers import SKILL_DIR

ALLOWED = {"name", "description", "license", "allowed-tools", "metadata"}


def frontmatter(text):
    assert text.startswith("---\n"), "frontmatter must start on line 1"
    end = text.index("\n---", 4)
    block = text[4:end]
    keys = re.findall(r"^([A-Za-z][A-Za-z-]*):", block, re.M)
    values = dict(re.findall(r"^([A-Za-z][A-Za-z-]*):[ \t]*(.*)$", block, re.M))
    return keys, values, text[end + 4:]


class TestSkillMd(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(SKILL_DIR, "SKILL.md"), encoding="utf-8") as fh:
            self.text = fh.read()
        self.keys, self.values, self.body = frontmatter(self.text)

    def test_only_cross_tool_keys(self):
        self.assertTrue(set(self.keys) <= ALLOWED, set(self.keys) - ALLOWED)
        self.assertIn("name", self.keys)
        self.assertIn("description", self.keys)

    def test_name_matches_directory(self):
        self.assertEqual(self.values["name"], os.path.basename(SKILL_DIR))
        self.assertRegex(self.values["name"], r"^[a-z0-9]+(-[a-z0-9]+)*$")

    def test_description_constraints(self):
        d = self.values["description"]
        self.assertTrue(d)
        self.assertLessEqual(len(d), 1024, len(d))
        self.assertNotIn("<", d)
        self.assertNotIn(">", d)
        self.assertNotIn("[TODO:", d)

    def test_body_has_no_todo_and_references_cli(self):
        self.assertNotRegex(self.body, r"(?m)^\s*\[TODO:")
        self.assertIn("${CLAUDE_SKILL_DIR}/scripts/outline-memory", self.body)
        self.assertIn("--scope", self.body)
        self.assertIn("<redacted>", self.body)
        self.assertLess(self.body.count("\n"), 500)

    def test_allowed_tools_matches_the_command_the_body_runs(self):
        self.assertIn("Bash(${CLAUDE_SKILL_DIR}/scripts/outline-memory *)", self.values["allowed-tools"])


class TestSupportingFiles(unittest.TestCase):
    def test_template_sections(self):
        with open(os.path.join(SKILL_DIR, "assets", "memory-template.md"), encoding="utf-8") as fh:
            t = fh.read()
        for h in ("## Summary", "## Context", "## What was done / Decisions", "## Learnings & gotchas",
                  "## Details", "## Open items / Follow-ups"):
            self.assertIn(h, t)
        self.assertNotIn("Provenance", t)

    def test_openai_yaml(self):
        with open(os.path.join(SKILL_DIR, "agents", "openai.yaml"), encoding="utf-8") as fh:
            y = fh.read()
        self.assertIn("display_name:", y)
        m = re.search(r'short_description:\s*"([^"]+)"', y)
        self.assertTrue(m)
        self.assertTrue(25 <= len(m.group(1)) <= 64, len(m.group(1)))
        self.assertIn("$outlinememory", y)

    def test_cli_is_executable(self):
        self.assertTrue(os.access(os.path.join(SKILL_DIR, "scripts", "outline-memory"), os.X_OK))


if __name__ == "__main__":
    unittest.main()
