import os
import socket
import subprocess
import tempfile
import unittest

from helpers import load_cli_module, write_private

cli = load_cli_module()


class TestConfigParser(unittest.TestCase):
    def test_flat_keys_quotes_and_comments(self):
        cfg = cli.parse_config_text(
            "# comment\nurl: \"https://outline.example.com/\"\n\ntoken_file: '~/tok'   # trailing\n"
            "collection: Memories\nroot:\nproxy: none\ntimeout: 12\n")
        self.assertEqual(cfg["url"], "https://outline.example.com/")
        self.assertEqual(cfg["token_file"], "~/tok")
        self.assertEqual(cfg["root"], "")
        self.assertEqual(cli.parse_config_text("url: https://x.example # c\nroot: # only a comment\n")["root"], "")
        self.assertEqual(cli.parse_config_text("url: \"https://x.example\"  # c\n")["url"], "https://x.example")
        self.assertEqual(cfg["timeout"], "12")
        self.assertEqual(cfg["projects"], {})

    def test_projects_block(self):
        cfg = cli.parse_config_text("url: https://x.example\nprojects:\n  my-repo: My Project\n  other: \"Other Name\"\nproxy: auto\n")
        self.assertEqual(cfg["projects"], {"my-repo": "My Project", "other": "Other Name"})
        self.assertEqual(cfg["proxy"], "auto")

    def test_bad_line_exit_3(self):
        with self.assertRaises(cli.OMError) as ctx:
            cli.parse_config_text("url: https://x.example\nthis is not yaml\n", "cfg")
        self.assertEqual(ctx.exception.code, 3)
        self.assertIn("cfg:2", ctx.exception.message)

    def test_unknown_key_is_ignored(self):
        cfg = cli.parse_config_text("url: https://x.example\nfuture_key: 1\n")
        self.assertNotIn("future_key", cfg)

    def test_load_config_validates_url_and_strips_api(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "c.yml")
            write_private(p, "url: https://outline.example.com/api/\n")
            cfg = cli.load_config(p)
            self.assertEqual(cfg["url"], "https://outline.example.com")
            self.assertEqual(cfg["collection"], "Memories")
            self.assertEqual(cfg["root"], "dev")
            self.assertEqual(cfg["timeout"], 30)
            write_private(p, "collection: X\n")
            with self.assertRaises(cli.OMError) as ctx:
                cli.load_config(p)
            self.assertEqual(ctx.exception.code, 3)

    def test_missing_config(self):
        with self.assertRaises(cli.OMError) as ctx:
            cli.load_config("/nonexistent/outline-memory.yml")
        self.assertEqual(ctx.exception.code, 3)
        self.assertIn("config.example.yml", ctx.exception.hint)

    def test_token_file_missing_and_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = {"token_file": os.path.join(tmp, "t"), "_path": "c"}
            with self.assertRaises(cli.OMError) as ctx:
                cli.load_token(cfg)
            self.assertEqual(ctx.exception.code, 3)
            write_private(cfg["token_file"], "\n")
            with self.assertRaises(cli.OMError):
                cli.load_token(cfg)
            write_private(cfg["token_file"], "ol_api_%s\n" % ("z" * 38))
            token, desc = cli.load_token(cfg)
            self.assertEqual(token, "ol_api_" + "z" * 38)
            self.assertIn("mode 600", desc)


class TestProjectDerivation(unittest.TestCase):
    def git(self, cwd, *args):
        subprocess.run(["git", "-C", cwd] + list(args), check=True, capture_output=True)

    def test_remote_toplevel_cwd_and_map(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = os.path.join(tmp, "checkout-dir")
            os.makedirs(os.path.join(repo, "sub"))
            self.git(tmp, "init", "-q", repo)
            # no remote → toplevel basename
            name, src = cli.derive_project(os.path.join(repo, "sub"), {})
            self.assertEqual((name, src), ("checkout-dir", "git toplevel"))
            # remote wins, .git stripped, scp-like url handled
            self.git(repo, "remote", "add", "origin", "git@example.com:someone/real-name.git")
            name, src = cli.derive_project(os.path.join(repo, "sub"), {})
            self.assertEqual((name, src), ("real-name", "git remote origin"))
            # https url
            self.git(repo, "remote", "set-url", "origin", "https://example.com/org/web-name.git")
            self.assertEqual(cli.derive_project(repo, {})[0], "web-name")
            # projects map
            name, src = cli.derive_project(repo, {"web-name": "Web Name"})
            self.assertEqual(name, "Web Name")
            self.assertIn("projects map", src)
            # --project wins over everything
            self.assertEqual(cli.derive_project(repo, {"x": "y"}, "explicit")[0], "explicit")
            # no git → cwd basename
            plain = os.path.join(tmp, "plain-dir")
            os.makedirs(plain)
            self.assertEqual(cli.derive_project(plain, {}), ("plain-dir", "cwd basename"))

    def test_repo_basename(self):
        self.assertEqual(cli.repo_basename("git@host:org/repo.git"), "repo")
        self.assertEqual(cli.repo_basename("https://host/org/repo"), "repo")
        self.assertEqual(cli.repo_basename("ssh://git@host:2222/org/repo.git/"), "repo")


class TestTitlesAndScan(unittest.TestCase):
    def test_build_title(self):
        self.assertEqual(cli.build_title("  Some   topic ", "2026-09-29"), "2026-09-29 Some topic")
        self.assertEqual(cli.build_title("2026-01-01 dated", "2026-09-29"), "2026-01-01 dated")
        self.assertEqual(cli.build_title("verbatim", "2026-09-29", no_date_prefix=True), "verbatim")
        long = cli.build_title("x" * 200, "2026-09-29")
        self.assertLessEqual(len(long), cli.MAX_TITLE)
        with self.assertRaises(cli.OMError):
            cli.build_title("   ", "2026-09-29")

    def test_unique_title(self):
        self.assertEqual(cli.unique_title("T", ["A"], False), "T")
        self.assertEqual(cli.unique_title("T", ["T"], False), "T (2)")
        self.assertEqual(cli.unique_title("T", ["T", "T (2)"], False), "T (3)")
        with self.assertRaises(cli.OMError) as ctx:
            cli.unique_title("T", ["T"], True)
        self.assertEqual(ctx.exception.code, 7)

    def test_secret_scan(self):
        self.assertEqual(cli.secret_scan("nothing here\nBearer <redacted>\ntoken issue --local host\n"), [])
        hits = cli.secret_scan("x\nkey %s\n" % ("ol_api_" + "b" * 30))
        self.assertEqual(hits, ["line 2: outline api key"])
        self.assertTrue(cli.secret_scan("-----BEGIN " + "OPENSSH PRIVATE KEY-----"))  # split so the repo scanner stays clean
        self.assertTrue(cli.secret_scan("password = %s" % ("p" * 20)))
        self.assertTrue(cli.secret_scan("SOME_SERVICE_TOKEN=%s" % ("Q" * 24)))
        self.assertFalse(cli.secret_scan("ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIKonHwC5 comment"))
        self.assertFalse(cli.secret_scan("token_file: ~/.outline-token\nMY_APP_TOKEN=<redacted>\n"
                                         "the token lives only in the server .env as MY_APP_TOKEN"))


class TestTransportDecision(unittest.TestCase):
    def test_auto_with_and_without_listener(self):
        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        port = srv.getsockname()[1]
        try:
            proxy, reason = cli.Transport._decide({"proxy": "auto", "proxy_probe": "127.0.0.1:%d" % port})
            self.assertEqual(proxy, "socks5h://127.0.0.1:%d" % port)
            self.assertIn("proxy port open", reason)
        finally:
            srv.close()
        proxy, reason = cli.Transport._decide({"proxy": "auto", "proxy_probe": "127.0.0.1:%d" % port})
        self.assertIsNone(proxy)
        self.assertIn("direct", reason)
        self.assertEqual(cli.Transport._decide({"proxy": "none"})[0], None)
        self.assertEqual(cli.Transport._decide({"proxy": "socks5h://h:1"})[0], "socks5h://h:1")
        self.assertEqual(cli.Transport._decide({"proxy": "http://h:3128"})[0], "http://h:3128")


if __name__ == "__main__":
    unittest.main()
