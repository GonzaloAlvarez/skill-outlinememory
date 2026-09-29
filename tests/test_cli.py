import datetime
import os
import re
import tempfile
import unittest

from fake_outline import FakeOutline
from helpers import make_env, run_cli, sample_body, server_state

TODAY = datetime.date.today().isoformat()


class CliCase(unittest.TestCase):
    scenario = "default"

    def setUp(self):
        self.fake = FakeOutline(self.scenario)
        self.url = self.fake.start()
        self.tmp = tempfile.TemporaryDirectory()
        self.config = make_env(self.tmp.name, self.url, self.fake.token)

    def tearDown(self):
        self.fake.stop()
        self.tmp.cleanup()

    def create(self, *extra, body=None, title="Topic one", project="proj"):
        return run_cli(["create", "--title", title, "--body", "-", "--project", project, "--tool", "Test Tool",
                        "--model", "test-model"] + list(extra), config=self.config, stdin=body or sample_body())

    def writes(self):
        return server_state(self.url)["writes"]


class TestCheck(CliCase):
    def test_check_green(self):
        r = run_cli(["check", "--project", "proj"], config=self.config)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for label in ("config", "token", "transport", "health", "auth", "collection", "tree", "root", "project"):
            self.assertIn(label, r.stdout)
        self.assertIn("direct (proxy: none)", r.stdout)
        self.assertIn("role member", r.stdout)
        self.assertIn("will create", r.stdout)
        self.assertNotIn(self.fake.token, r.stdout + r.stderr)

    def test_check_missing_config(self):
        r = run_cli(["check"], config=os.path.join(self.tmp.name, "nope.yml"))
        self.assertEqual(r.returncode, 3)
        self.assertIn("config missing", r.stdout)
        self.assertIn("hint:", r.stdout)

    def test_check_bad_token(self):
        cfg = make_env(self.tmp.name, self.url, "ol_api_" + "x" * 38)
        r = run_cli(["check"], config=cfg)
        self.assertEqual(r.returncode, 5, r.stdout)
        self.assertIn("FAIL", r.stdout)
        self.assertIn("HTTP 401", r.stdout)


class TestCheckNoCollection(CliCase):
    scenario = "no_collection"

    def test_exit_6(self):
        r = run_cli(["check"], config=self.config)
        self.assertEqual(r.returncode, 6, r.stdout)
        self.assertIn("not found", r.stdout)
        self.assertIn("visible: Other", r.stdout)


class TestCheckHtml404(CliCase):
    scenario = "html_404"

    def test_exit_4_with_public_host_hint(self):
        r = run_cli(["check"], config=self.config)
        self.assertEqual(r.returncode, 4, r.stdout)
        self.assertIn("health", r.stdout)
        self.assertIn("FAIL", r.stdout)

    def test_create_exit_4(self):
        r = self.create()
        self.assertEqual(r.returncode, 4, r.stderr)
        self.assertIn("HTML", r.stderr)
        self.assertIn("hint:", r.stderr)


class TestCheckAdmin(CliCase):
    scenario = "admin_user"

    def test_admin_hint(self):
        r = run_cli(["check"], config=self.config)
        self.assertEqual(r.returncode, 0)
        self.assertIn("role admin", r.stdout)
        self.assertIn("confined member user", r.stdout)


class TestCreateEmptyCollection(CliCase):
    def test_three_writes_root_project_page(self):
        r = self.create()
        self.assertEqual(r.returncode, 0, r.stderr)
        w = self.writes()
        self.assertEqual([x["title"] for x in w], ["dev", "proj", "%s Topic one" % TODAY])
        self.assertEqual(w[0]["text"], "")
        self.assertEqual(w[1]["text"], "")
        self.assertIsNone(w[0]["parentDocumentId"])
        self.assertEqual(w[1]["parentDocumentId"], w[0]["id"])
        self.assertEqual(w[2]["parentDocumentId"], w[1]["id"])
        page = w[2]["text"]
        self.assertTrue(page.startswith("> Memory · Test Tool · %s · project proj" % TODAY), page[:80])
        self.assertIn("## Summary", page)
        self.assertIn("## Provenance", page)
        self.assertIn("| Tool | Test Tool · test-model |", page)
        self.assertIn("| Scope | whole session |", page)
        self.assertIn("| Written by | outlinememory", page)
        self.assertIn("root: created dev", r.stdout)
        self.assertIn("project: created proj", r.stdout)
        self.assertRegex(r.stdout, r'created: "%s Topic one" → %s/doc/' % (TODAY, re.escape(self.url)))

    def test_scope_and_session_recorded(self):
        r = self.create("--scope", "only the pinhole thread", "--session", "abc-123")
        self.assertEqual(r.returncode, 0, r.stderr)
        page = self.writes()[-1]["text"]
        self.assertIn("| Scope | only the pinhole thread |", page)
        self.assertIn("| Session | abc-123 |", page)

    def test_json_output(self):
        import json
        r = run_cli(["--json", "create", "--title", "T", "--body", "-", "--project", "p", "--tool", "X"],
                    config=self.config, stdin=sample_body())
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads(r.stdout)
        self.assertTrue(data["ok"])
        self.assertTrue(data["parent"]["created"])
        self.assertTrue(data["root"]["created"])
        self.assertEqual(data["title"], "%s T" % TODAY)
        self.assertEqual(data["transport"], "direct")

    def test_dry_run_writes_nothing(self):
        r = self.create("--dry-run")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.writes(), [])
        self.assertIn("dry-run plan:", r.stdout)
        self.assertIn("root: dev will be created", r.stdout)
        self.assertIn("project: proj will be created", r.stdout)
        self.assertIn("---- document ----", r.stdout)
        self.assertIn("## Provenance", r.stdout)

    def test_secret_guard_blocks_before_network(self):
        body = sample_body() + "\nthe key is %s\n" % ("ol_api_" + "a" * 30)
        r = self.create(body=body)
        self.assertEqual(r.returncode, 8, r.stderr)
        self.assertIn("outline api key", r.stderr)
        self.assertNotIn("a" * 30, r.stderr)
        self.assertEqual(self.writes(), [])

    def test_secret_guard_assignment(self):
        body = sample_body() + "\nSOME_SERVICE_TOKEN=%s\n" % ("Q" * 24)
        r = self.create(body=body)
        self.assertEqual(r.returncode, 8, r.stderr)

    def test_redacted_marker_passes(self):
        body = sample_body() + "\nMY_APP_TOKEN=<redacted> lives in the server .env\n"
        r = self.create(body=body)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_empty_body_is_usage_error(self):
        r = self.create(body="  \n")
        self.assertEqual(r.returncode, 2)

    def test_title_with_date_is_not_prefixed_twice(self):
        r = self.create(title="2026-01-05 Already dated")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.writes()[-1]["title"], "2026-01-05 Already dated")

    def test_no_date_prefix_flag(self):
        r = self.create("--no-date-prefix", title="Verbatim title")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.writes()[-1]["title"], "Verbatim title")

    def test_verify_flag(self):
        r = self.create("--verify")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_root_disabled_puts_project_at_top_level(self):
        cfg = make_env(self.tmp.name, self.url, self.fake.token, root="")
        r = run_cli(["create", "--title", "T", "--body", "-", "--project", "p", "--tool", "X"], config=cfg,
                    stdin=sample_body())
        self.assertEqual(r.returncode, 0, r.stderr)
        w = self.writes()
        self.assertEqual([x["title"] for x in w], ["p", "%s T" % TODAY])
        self.assertIsNone(w[0]["parentDocumentId"])


class TestCreateExistingRoot(CliCase):
    scenario = "existing_root"

    def test_two_writes(self):
        r = self.create()
        self.assertEqual(r.returncode, 0, r.stderr)
        w = self.writes()
        self.assertEqual([x["title"] for x in w], ["proj", "%s Topic one" % TODAY])
        self.assertNotIn("root: created", r.stdout)
        self.assertIn("project: created proj", r.stdout)
        tree = server_state(self.url)["tree"]
        self.assertEqual(len(tree), 1)  # still exactly one top-level page
        self.assertEqual(tree[0]["title"], "dev")


class TestCreateExistingParent(CliCase):
    scenario = "existing_parent_with_child"

    def test_one_write(self):
        r = self.create(project="my-service")
        self.assertEqual(r.returncode, 0, r.stderr)
        w = self.writes()
        self.assertEqual(len(w), 1)
        self.assertEqual(w[0]["title"], "%s Topic one" % TODAY)
        self.assertNotIn("created dev", r.stdout)
        self.assertNotIn("created my-service", r.stdout)

    def test_collision_suffix(self):
        r = self.create(project="my-service", title="2026-01-01 Existing topic")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.writes()[-1]["title"], "2026-01-01 Existing topic (2)")
        self.assertIn("warning: title", r.stderr)

    def test_collision_strict(self):
        r = self.create("--strict-title", project="my-service", title="2026-01-01 Existing topic")
        self.assertEqual(r.returncode, 7, r.stderr)
        self.assertEqual(self.writes(), [])

    def test_list(self):
        r = run_cli(["list", "--project", "my-service"], config=self.config)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("root: dev exists", r.stdout)
        self.assertIn("project: my-service exists", r.stdout)
        self.assertIn("- 2026-01-01 Existing topic", r.stdout)

    def test_parent_id_override(self):
        tree = server_state(self.url)["tree"]
        target = tree[0]["children"][0]["children"][0]["id"]  # the existing memory page
        r = self.create("--parent-id", target, project="ignored")
        self.assertEqual(r.returncode, 0, r.stderr)
        w = self.writes()
        self.assertEqual(len(w), 1)
        self.assertEqual(w[0]["parentDocumentId"], target)

    def test_parent_id_unknown(self):
        r = self.create("--parent-id", "00000000-0000-0000-0000-000000000000")
        self.assertEqual(r.returncode, 7, r.stderr)


class TestDupParent(CliCase):
    scenario = "dup_parent"

    def test_ambiguous_root(self):
        r = self.create()
        self.assertEqual(r.returncode, 7, r.stderr)
        self.assertIn("--parent-id", r.stderr)
        self.assertEqual(self.writes(), [])


class TestForeignTree(CliCase):
    scenario = "foreign_tree"

    def test_personal_untouched(self):
        before = server_state(self.url)["tree"]
        r = self.create()
        self.assertEqual(r.returncode, 0, r.stderr)
        after = server_state(self.url)["tree"]
        self.assertEqual(len(after), 2)
        personal_before = [n for n in before if n["title"] == "personal"][0]
        personal_after = [n for n in after if n["title"] == "personal"][0]
        self.assertEqual(personal_before, personal_after)
        self.assertEqual([x["title"] for x in self.writes()], ["dev", "proj", "%s Topic one" % TODAY])


class TestUnauthorized(CliCase):
    scenario = "unauthorized"

    def test_exit_5(self):
        r = self.create()
        self.assertEqual(r.returncode, 5, r.stderr)
        self.assertIn("HTTP 401", r.stderr)
        self.assertEqual(self.writes(), [])


if __name__ == "__main__":
    unittest.main()
