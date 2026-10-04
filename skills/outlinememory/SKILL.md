---
name: outlinememory
description: Save a memory of the current conversation to the operator's self-hosted Outline wiki as a new page under the per-project parent page in the Memories collection, with summary, context, decisions, learnings and gotchas, details and open items, secrets redacted. Use when the user says "create memory of this conversation", "save this conversation to outline", "remember this session", or invokes /outlinememory or $outlinememory, optionally with a topic or a scope such as "only the part about X". Can upload images the user points at and embed them in the page. Requires the local outline-memory config and token described in the skill README; the bundled scripts/outline-memory CLI performs the API calls. Not for reading, searching or editing existing memories.
license: MIT
allowed-tools: Bash(${CLAUDE_SKILL_DIR}/scripts/outline-memory *)
metadata:
  short-description: Save this conversation as an Outline memory
  version: "0.2.0"
  homepage: https://github.com/GonzaloAlvarez/skill-outlinememory
---

# outlinememory — save this conversation as an Outline memory page

You are writing a durable memory of the conversation you are in, for a human and for
other agents that will read it later without your context. The bundled CLI creates the
page; you write the content.

**Paths.** In Claude Code `${CLAUDE_SKILL_DIR}` below is already expanded. In Codex it is
not: read `${CLAUDE_SKILL_DIR}` as the directory that contains this SKILL.md (for example
`~/.codex/skills/outlinememory`). The CLI is `${CLAUDE_SKILL_DIR}/scripts/outline-memory`.

**Topic hint.** Anything the user typed after the command is the topic and/or scope
(Claude Code passes it as `ARGUMENTS`; in Codex it is the rest of the user's message).

## Step 1 — decide the scope

The memory covers the **whole conversation** unless the user narrows it: a topic after the
command (`/outlinememory the pinhole ssh work, not the skill`), "only the part about X",
"everything since we started Y", "the last hour". When narrowed:

* summarize **only** that thread and leave the rest out entirely (no "we also did…");
* make the title name the thread;
* say in the Context section that this is a partial memory of a longer session;
* pass `--scope "<one line describing the thread>"` so Provenance records it.

One session may yield several memories, one per thread; distinct titles keep them apart.

## Step 2 — write the body

Use the section skeleton in `${CLAUDE_SKILL_DIR}/assets/memory-template.md` and fill every
section (write "none" rather than deleting a heading):

* **Summary** — 3 to 6 sentences: what was the goal, what is the outcome, what changed.
* **Context** — why this came up, what prompted it, constraints given by the user.
* **What was done / Decisions** — the decisions and their reasons; what was built or changed.
* **Learnings & gotchas** — the durable part: things that surprised you, root causes,
  wrong assumptions corrected, things to do differently next time.
* **Details** — exact file paths, versions, commands, identifiers, error messages and their
  fixes. Prefer precise facts over narrative.
* **Open items / Follow-ups** — what is pending, deferred or still unverified.

Quality bar: durable over chronological; no transcript replay; exact names and paths.
Markdown rules for Outline: keep any `>` blockquote on a single line; use `* ` bullets;
tables are fine; do not write a Provenance section (the CLI appends it); do not start with
a level-1 heading that repeats the title.

**Images.** Only when the user asked for a screenshot, diagram or other file to be part of
the memory and it exists on disk: reference it in the body as `![caption](attach:<file name>)`
and pass `--attach <path>` for that file in Step 4 (repeat both for several files). The CLI
uploads each file first and swaps the placeholder for the real URL; a file passed without a
placeholder is listed under an `## Attachments` heading. Attach only files the user pointed at
or that you produced for them — never configuration files, logs or anything that may contain
a secret, and never anything you have not looked at.

**Redaction — hard rule.** Never include tokens, API keys, passwords, private keys, cookie
or session values, `.env` contents or whole configuration files. Replace each with
`<redacted>`. Describe where a secret lives, never its value. The CLI refuses a body that
looks like it contains a secret (exit 8): fix the body, never bypass the check.

## Step 3 — pick title and project

* Title: a short topic (aim for 60 characters or fewer, sentence case). The CLI prefixes the
  date (`YYYY-MM-DD topic`) and adds a numbered suffix if the title already exists.
* Project: the CLI derives it from the working directory's git repository. If the
  directory is not a repository, or the derived name is generic (`dev`, `src`, a home
  directory), or the thread belongs to another repository, pass `--project <name>`.
  `${CLAUDE_SKILL_DIR}/scripts/outline-memory project` prints what would be derived.

## Step 4 — create the page

Run one command with the body on stdin (quoted heredoc, so nothing inside is expanded):

```
${CLAUDE_SKILL_DIR}/scripts/outline-memory create \
  --title "<topic>" --body - --tool "Claude Code" --model "<your model id>" \
  [--scope "<thread>"] [--project "<name>"] [--attach <path>]... <<'OUTLINE_MEMORY_BODY'
## Summary
...
OUTLINE_MEMORY_BODY
```

In Codex use `--tool "Codex CLI"`. The command needs network access; when Codex asks to run
it outside the sandbox, approve that single run. Do not change sandbox settings.

If a heredoc is not possible, write the body to a temporary file and pass `--body <file>`.
Useful flags the user may ask for: `--dry-run` (resolve and print the final page, write
nothing), `--strict-title` (fail instead of numbering), `--parent-id <id>` (put the page
under a specific existing page).

## Step 5 — report

Quote the CLI's final `created: "<title>" → <url>` line to the user. Mention when the CLI
reports that it created the `root:` or `project:` container pages, and list any `attached:`
lines (one per uploaded file).

## On failure

Run `${CLAUDE_SKILL_DIR}/scripts/outline-memory check` once and report the failing line and
its `hint:` verbatim. Retry the create at most once. Never print the token or the contents
of the token file. If the config or token is missing, point the user to the README in the
skill repository and stop.
