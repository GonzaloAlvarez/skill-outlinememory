# skill-outlinememory

An [Agent Skill](https://agentskills.io) for **Claude Code** and **OpenAI Codex** that saves a
memory of the current conversation as a page in a self-hosted
[Outline](https://www.getoutline.com) wiki: summary, context, decisions, learnings and
gotchas, details, open items, plus a provenance table (date, tool, model, host, project,
branch). Pages are organised per project inside one collection:

```
Memories                      ← the collection (configurable)
└── dev                       ← root container page (configurable, may be disabled)
    ├── my-service            ← one container per project (derived from the git repo)
    │   ├── 2026-09-29 Rate limiter redesign
    │   └── 2026-10-02 Debugging the flaky deploy
    └── another-repo
        └── 2026-09-30 …
```

Invoke it with `/outlinememory` in Claude Code, `$outlinememory` in Codex, or just say
"create memory of this conversation". Add a topic or a scope: `/outlinememory only the part
about the deploy pipeline` writes a memory of that thread alone.

Nothing about your Outline instance lives in this repository. The URL, collection and
transport settings go into `~/.outline-memory.yml`; the API key goes into
`~/.outline-token`.

## Install

```sh
git clone https://github.com/GonzaloAlvarez/skill-outlinememory ~/dev/skill-outlinememory
cd ~/dev/skill-outlinememory
./install.sh                                     # symlinks into ~/.claude/skills, ~/.codex/skills, ~/.agents/skills
cp config.example.yml ~/.outline-memory.yml && chmod 600 ~/.outline-memory.yml   # set url:
(umask 077; printf '%s\n' ol_api_YOUR_KEY > ~/.outline-token)
skills/outlinememory/scripts/outline-memory check
```

Pointing an agent at this folder works too: `CLAUDE.md`/`AGENTS.md` tell Claude Code and
Codex to run the same steps. `./install.sh --uninstall` removes the links and leaves your
config and token alone. `./install.sh --copy` copies instead of linking (see Codex notes).
Re-run `./install.sh` after `git pull` only if you used `--copy`; symlinks pick up updates
automatically.

Requirements: `python3` (3.9+), `curl`, `git` (for project derivation). No Python packages.

## Configuration — `~/.outline-memory.yml`

Flat `key: value` lines; `#` comments; quotes optional. Keep the file mode 0600.

| key | default | meaning |
|---|---|---|
| `url` | *(required)* | Outline base URL, e.g. `https://outline.example.com` — no trailing slash, no `/api` |
| `token_file` | `~/.outline-token` | file containing the API key (`ol_api_…`), one line, mode 0600 |
| `token` | – | inline key; discouraged, wins over `token_file` with a warning |
| `collection` | `Memories` | target collection, resolved by name |
| `root` | `dev` | top-level container page; empty value → project pages directly at the top level |
| `proxy` | `auto` | `auto` \| `none` \| `socks5h://host:port` \| `http://host:port` |
| `proxy_probe` | `127.0.0.1:1055` | in `auto` mode, use `socks5h://<proxy_probe>` when something listens there |
| `ca_file` | – | CA bundle passed to `curl --cacert` when Outline presents a private certificate |
| `timeout` | `30` | seconds per request |
| `projects:` | – | indented block `derived-name: Display Name` renaming projects for new pages |

`OUTLINE_MEMORY_CONFIG=/path/to/file` or `--config` selects another config file.

### The API key

Create an Outline API key (Settings → API) for the user that should author the memories,
ideally a dedicated user whose only writable collection is the memories collection, and
scope the key to what the CLI needs:

```
auth.info collections.list collections.documents documents.create documents.info
```

A key never exceeds its user's permissions, so a leaked `~/.outline-token` scoped this way
can only add pages where that user can already write. `check` warns when the key belongs to
an admin.

### Transport

* **Same network / VPN as Outline** → `proxy: none` (or `auto` with nothing listening).
* **Through a local SOCKS5 proxy** (for example a container that tunnels into the network
  where Outline lives) → `proxy: auto` probes `proxy_probe` and uses `socks5h://…` when the
  port is open, so name resolution happens on the far side of the proxy.
* **Private CA** → `ca_file: /path/to/root.pem`. The CLI never disables TLS verification.

## Usage

Inside Claude Code or Codex:

```
/outlinememory                                  # whole conversation
/outlinememory the migration work, not the UI   # one thread only
$outlinememory                                  # Codex
```

The agent writes the six sections from `skills/outlinememory/assets/memory-template.md`,
redacts secrets, and runs the CLI, which adds the provenance table and creates the page. It
reports the page URL when done.

### CLI

```
outline-memory [--config PATH] [--json] <command>
  check                       config → token → transport → health → auth → collection → tree → root/project
  project [--cwd DIR]         print the derived project name
  list    [--project P]       titles already under root/project
  create  --title T --body FILE|- [--project P] [--parent-id ID] [--tool T] [--model M]
          [--session S] [--scope TEXT] [--dry-run] [--strict-title] [--verify] [--no-date-prefix]
  version
```

Project derivation: `git remote get-url origin` basename → `git rev-parse --show-toplevel`
basename → working-directory basename → `projects:` map. `--project` overrides.

Exit codes: `0` ok · `2` usage · `3` config/token · `4` transport · `5` auth/permission ·
`6` collection not found · `7` ambiguous parent or `--strict-title` collision · `8` the body
looks like it contains a secret · `9` other Outline API error. `--json` prints one JSON object
on stdout, also for errors.

### What a page looks like

```
> Memory · Claude Code · 2026-09-29 · project my-service

## Summary
…
## Provenance

| Field | Value |
|---|---|
| Date | 2026-09-29 21:14 +0000 |
| Tool | Claude Code · model-id |
| Host | laptop |
| Project | my-service |
| Repo path | /home/me/src/my-service |
| Branch | main @ f4459bb |
| Scope | whole session |
| Session | - |
| Written by | outlinememory 0.1.0 |
```

## Codex notes

* Skills are invoked as `$outlinememory` (there is no per-skill slash command in Codex).
* Codex's default sandbox has no network. When the skill runs the CLI, Codex asks to run that
  command outside the sandbox — approve it. You can avoid the prompt for good with
  `[sandbox_workspace_write] network_access = true` in `~/.codex/config.toml`, but that
  applies to every command, so the prompt is the safer default.
* Codex may ignore a symlinked skill folder. If `/skills` does not list `outlinememory`,
  either add `allow_symlinked_codex_home = true` to `~/.codex/config.toml` or run
  `./install.sh --copy --codex-only`.

## Claude Code notes

* The skill's `allowed-tools` grants exactly one command, the bundled CLI, so creating a memory
  needs no permission prompt. Review `skills/outlinememory/SKILL.md` before installing, as you
  would any skill.
* The skill must run in the main conversation (it summarises what it can see), so it does not
  use a forked context.

## Memories of past sessions

Resume the old session and invoke the skill there:

```sh
claude --resume <session-id> --fork-session      # then /outlinememory [scope]
codex resume <session-id> '$outlinememory'
```

A `sessions` sub-command that lists, exports and batch-syncs past transcripts is a planned
follow-up.

## Troubleshooting

| symptom | `check` line | fix |
|---|---|---|
| `config missing` | config | `cp config.example.yml ~/.outline-memory.yml`, set `url:` |
| `token file missing` / mode warning | token | create `~/.outline-token`, `chmod 600` |
| `HTTP 404 with an HTML body` | health | you reached a public or wrong host — start the SOCKS proxy, check `url:` |
| `curl: … could not resolve host` | health | not on the right network; start the proxy or set `proxy:` |
| `certificate verify failed` | health | set `ca_file:` to your private CA bundle |
| `HTTP 401` | auth | key invalid or expired — create a new one |
| `HTTP 403` on `documents.create` | create | the key lacks the scope, or its user cannot write to the collection |
| `collection … not found` | collection | wrong `collection:` name, or the user cannot see it |
| `2 top-level pages are titled 'dev'` | root | rename one in Outline or pass `--parent-id` |
| exit 8 | create | the body contains something that looks like a secret; redact it |

## Development

```sh
./test          # unit tests (offline fake Outline + real curl), secret scan, Codex validator if installed
```

`scripts/no-secrets-check` runs as a pre-commit hook (`git config core.hooksPath .githooks`).
Put patterns that identify *your* instance (domains, host names, user names) into
`.no-secrets-local` — it is gitignored on purpose. To scan the whole history before
publishing (commit headers and the scanner's own regex source excluded):

```sh
git log -p --format= -- . ':!scripts/no-secrets-check' | scripts/no-secrets-check --stdin
```

## License

MIT
