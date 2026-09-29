"""Shared helpers: load the extension-less CLI as a module, run it as a subprocess."""
import importlib.machinery
import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL_DIR = os.path.join(REPO, "skills", "outlinememory")
CLI = os.path.join(SKILL_DIR, "scripts", "outline-memory")
INSTALL = os.path.join(REPO, "install.sh")


def load_cli_module():
    loader = importlib.machinery.SourceFileLoader("outline_memory_cli", CLI)
    spec = importlib.util.spec_from_loader("outline_memory_cli", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def write_private(path, content):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(content)
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


def make_env(tmp, url, token, root="dev", extra=""):
    """Create token file + config in tmp; return the config path."""
    token_path = os.path.join(tmp, "token")
    write_private(token_path, token + "\n")
    cfg_path = os.path.join(tmp, "config.yml")
    root_line = "root: %s\n" % root if root is not None else ""
    write_private(cfg_path, "url: %s\ntoken_file: %s\ncollection: Memories\n%sproxy: none\ntimeout: 10\n%s"
                  % (url, token_path, root_line, extra))
    return cfg_path


def run_cli(args, config=None, stdin=None, env=None, cwd=None):
    cmd = [sys.executable, CLI]
    if config:
        cmd += ["--config", config]
    cmd += args
    full_env = dict(os.environ)
    full_env.pop("CLAUDECODE", None)
    for k in list(full_env):
        if k.startswith("CODEX_"):
            full_env.pop(k)
    if env:
        full_env.update(env)
    return subprocess.run(cmd, input=stdin, capture_output=True, text=True, env=full_env, cwd=cwd, timeout=60)


def server_state(url):
    with urllib.request.urlopen(url + "/__state", timeout=5) as resp:
        return json.loads(resp.read().decode())


def sample_body():
    return ("## Summary\n\nWe built a thing and it works.\n\n## Context\n\nA user asked for it.\n\n"
            "## What was done / Decisions\n\n* decided X because Y\n\n## Learnings & gotchas\n\n* Z surprised us\n\n"
            "## Details\n\n* path `/opt/example/app`\n\n## Open items / Follow-ups\n\n* none\n")
