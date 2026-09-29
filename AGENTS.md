# For agents opening this folder

This repository is an **agent skill** (`skills/outlinememory/SKILL.md`) that saves a memory of
the current conversation as a page in a self-hosted Outline wiki. To make it work on this
machine:

1. Run `./install.sh` — it links the skill into `~/.claude/skills/`, `~/.codex/skills/` and
   `~/.agents/skills/` (idempotent; `--copy` if a tool refuses symlinks, `--uninstall` to remove).
2. Create `~/.outline-memory.yml` from `config.example.yml` and set `url:` to the Outline
   instance. Never put the URL or any token into this repository.
3. Save the Outline API key to `~/.outline-token` with mode 0600.
4. Run `skills/outlinememory/scripts/outline-memory check` until every line is `ok`.
5. Invoke the skill: `/outlinememory` in Claude Code, `$outlinememory` in Codex, or say
   "create memory of this conversation".

Before committing: run `./test` (unit tests + secret scan + skill validator). This repo is
public — no hostnames, IPs, e-mail addresses or tokens in any tracked file.
