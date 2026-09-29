import os
import subprocess
import tempfile
import unittest

from helpers import INSTALL, SKILL_DIR


def run_install(home, *args):
    env = dict(os.environ, HOME=home, CODEX_HOME=os.path.join(home, ".codex"))
    env.pop("OUTLINE_MEMORY_CONFIG", None)
    return subprocess.run(["/bin/bash", INSTALL, "--no-check"] + list(args), env=env, capture_output=True,
                          text=True, timeout=60)


class TestInstall(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = self.tmp.name
        self.targets = [os.path.join(self.home, ".claude", "skills", "outlinememory"),
                        os.path.join(self.home, ".codex", "skills", "outlinememory"),
                        os.path.join(self.home, ".agents", "skills", "outlinememory")]
        self.src_real = os.path.realpath(SKILL_DIR)

    def tearDown(self):
        self.tmp.cleanup()

    def test_symlinks_idempotent_and_uninstall(self):
        r = run_install(self.home)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for t in self.targets:
            self.assertTrue(os.path.islink(t), t)
            self.assertEqual(os.path.realpath(t), self.src_real)
        self.assertIn("allow_symlinked_codex_home", r.stdout)  # Codex caveat is surfaced
        r2 = run_install(self.home)
        self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
        self.assertEqual(r2.stdout.count("already linked"), 3)
        r3 = run_install(self.home, "--uninstall")
        self.assertEqual(r3.returncode, 0, r3.stdout + r3.stderr)
        for t in self.targets:
            self.assertFalse(os.path.lexists(t), t)

    def test_foreign_directory_is_refused(self):
        foreign = self.targets[0]
        os.makedirs(foreign)
        with open(os.path.join(foreign, "SKILL.md"), "w") as fh:
            fh.write("someone else's skill\n")
        r = run_install(self.home, "--claude-only")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("did not create", r.stderr)
        self.assertTrue(os.path.isdir(foreign) and not os.path.islink(foreign))
        with open(os.path.join(foreign, "SKILL.md")) as fh:
            self.assertEqual(fh.read(), "someone else's skill\n")
        r = run_install(self.home, "--claude-only", "--uninstall")
        self.assertEqual(r.returncode, 0)
        self.assertIn("kept", r.stdout)
        self.assertTrue(os.path.isdir(foreign))

    def test_foreign_symlink_needs_force(self):
        t = self.targets[0]
        os.makedirs(os.path.dirname(t))
        os.symlink(self.home, t)
        r = run_install(self.home, "--claude-only")
        self.assertEqual(r.returncode, 1)
        self.assertIn("--force", r.stderr)
        r = run_install(self.home, "--claude-only", "--force")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(os.path.realpath(t), self.src_real)

    def test_copy_mode_marker_and_uninstall(self):
        r = run_install(self.home, "--copy", "--codex-only")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(os.path.lexists(self.targets[0]))
        for t in self.targets[1:]:
            self.assertTrue(os.path.isdir(t) and not os.path.islink(t), t)
            self.assertTrue(os.path.isfile(os.path.join(t, "SKILL.md")))
            with open(os.path.join(t, ".installed-from")) as fh:
                self.assertEqual(fh.read().strip(), self.src_real)
        # re-running refreshes the copies
        r = run_install(self.home, "--copy", "--codex-only")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        # switching to link mode replaces our marked copies
        r = run_install(self.home, "--codex-only")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for t in self.targets[1:]:
            self.assertTrue(os.path.islink(t), t)
        r = run_install(self.home, "--uninstall")
        self.assertEqual(r.returncode, 0)
        for t in self.targets:
            self.assertFalse(os.path.lexists(t), t)

    def test_dry_run_creates_nothing(self):
        r = run_install(self.home, "--dry-run")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("would:", r.stdout)
        for t in self.targets:
            self.assertFalse(os.path.lexists(t), t)

    def test_config_and_token_left_alone_by_uninstall(self):
        cfg = os.path.join(self.home, ".outline-memory.yml")
        with open(cfg, "w") as fh:
            fh.write("url: https://outline.example.com\n")
        run_install(self.home)
        r = run_install(self.home, "--uninstall")
        self.assertEqual(r.returncode, 0)
        self.assertTrue(os.path.exists(cfg))
        self.assertIn("left in place", r.stdout)


if __name__ == "__main__":
    unittest.main()
