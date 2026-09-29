#!/bin/bash
# install.sh — link (or copy) the outlinememory skill into the skill directories of
# Claude Code (~/.claude/skills) and Codex (~/.codex/skills, ~/.agents/skills).
# Idempotent. Never deletes a directory it did not create. Works with bash 3.2.
set -euo pipefail

usage() {
  cat <<'EOF'
usage: ./install.sh [--copy] [--claude-only | --codex-only] [--uninstall] [--no-check] [--dry-run] [--force]

  (default)      symlink the skill into every known skill directory
  --copy         copy instead of symlinking (for tools that refuse symlinked skills)
  --claude-only  only ~/.claude/skills/outlinememory
  --codex-only   only $CODEX_HOME/skills/outlinememory and ~/.agents/skills/outlinememory
  --uninstall    remove what this script installed (config and token are left alone)
  --no-check     skip running `outline-memory check` at the end
  --dry-run      print what would be done
  --force        replace a symlink that points somewhere else
EOF
}

MODE=link SCOPE=all UNINSTALL=0 CHECK=1 DRY=0 FORCE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --copy) MODE=copy ;;
    --claude-only) SCOPE=claude ;;
    --codex-only) SCOPE=codex ;;
    --uninstall) UNINSTALL=1 ;;
    --no-check) CHECK=0 ;;
    --dry-run) DRY=1 ;;
    --force) FORCE=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

HERE=$(cd "$(dirname "$0")" && pwd -P)
NAME=outlinememory
SRC="$HERE/skills/$NAME"
MARKER=.installed-from
CODEX_HOME_DIR=${CODEX_HOME:-$HOME/.codex}
FAILED=0

[ -f "$SRC/SKILL.md" ] || { echo "error: $SRC/SKILL.md not found" >&2; exit 1; }

log()  { printf '  %s\n' "$*"; }
fail() { printf '  FAIL %s\n' "$*" >&2; FAILED=1; }
run()  { if [ "$DRY" = 1 ]; then printf '  would: %s\n' "$*"; else "$@"; fi; }

# absolute, symlink-resolved path of a directory (or of a link's target)
realdir() { (cd "$1" 2>/dev/null && pwd -P) || printf '%s' "$1"; }
link_target() { local raw; raw=$(readlink "$1"); case "$raw" in /*) realdir "$raw" ;; *) realdir "$(dirname "$1")/$raw" ;; esac; }

SRC_REAL=$(realdir "$SRC")

targets=""
case "$SCOPE" in all|claude) targets="$targets $HOME/.claude/skills/$NAME" ;; esac
case "$SCOPE" in all|codex)  targets="$targets $CODEX_HOME_DIR/skills/$NAME $HOME/.agents/skills/$NAME" ;; esac

do_install() {  # <target>
  local t=$1
  run mkdir -p "$(dirname "$t")"
  if [ "$MODE" = link ]; then
    run ln -s "$SRC_REAL" "$t"; log "linked  $t → $SRC_REAL"
  else
    run cp -R "$SRC_REAL" "$t"
    if [ "$DRY" = 1 ]; then log "would: write $t/$MARKER"; else printf '%s\n' "$SRC_REAL" >"$t/$MARKER"; fi
    log "copied  $t (marker $MARKER)"
  fi
}

install_target() {  # <target>
  local t=$1 dest
  if [ -L "$t" ]; then
    dest=$(link_target "$t")
    if [ "$dest" = "$SRC_REAL" ]; then
      if [ "$MODE" = copy ]; then run rm "$t"; do_install "$t"; else log "ok      $t (already linked)"; fi
    elif [ "$FORCE" = 1 ]; then
      run rm "$t"; do_install "$t"
    else
      fail "$t is a symlink to $dest — not ours; use --force to replace it"
    fi
  elif [ -d "$t" ]; then
    if [ -f "$t/$MARKER" ]; then
      run rm -rf "$t"; do_install "$t"        # a copy we made earlier: refresh it
    else
      fail "$t is a directory this script did not create — remove it yourself, then re-run"
    fi
  elif [ -e "$t" ]; then
    fail "$t exists and is neither a directory nor a symlink"
  else
    do_install "$t"
  fi
}

uninstall_target() {  # <target>
  local t=$1
  if [ -L "$t" ]; then
    if [ "$(link_target "$t")" = "$SRC_REAL" ]; then run rm "$t"; log "removed $t"; else log "kept    $t (symlink to somewhere else)"; fi
  elif [ -d "$t" ] && [ -f "$t/$MARKER" ] && [ "$(cat "$t/$MARKER")" = "$SRC_REAL" ]; then
    run rm -rf "$t"; log "removed $t (copy made by this script)"
  elif [ -e "$t" ]; then
    log "kept    $t (not installed by this script)"
  fi
}

if [ "$UNINSTALL" = 1 ]; then
  echo "uninstalling $NAME"
  for t in $targets; do uninstall_target "$t"; done
  echo "left in place: ~/.outline-memory.yml and ~/.outline-token (delete them yourself if wanted)"
  exit 0
fi

echo "installing $NAME from $SRC_REAL ($MODE)"
[ "$DRY" = 1 ] || chmod +x "$SRC/scripts/outline-memory"
for t in $targets; do install_target "$t"; done

# Codex may skip symlinked skill folders unless told to trust them.
case "$SCOPE" in all|codex)
  if [ "$MODE" = link ] && ! grep -Eq '^[[:space:]]*allow_symlinked_codex_home[[:space:]]*=[[:space:]]*true' "$CODEX_HOME_DIR/config.toml" 2>/dev/null; then
    log "note    Codex may ignore symlinked skills. If \`/skills\` in Codex does not list $NAME, either add"
    log "        allow_symlinked_codex_home = true   to $CODEX_HOME_DIR/config.toml, or run: ./install.sh --copy --codex-only"
  fi ;;
esac

# Validate the skill with the validator Codex ships, when available.
VALIDATOR="$CODEX_HOME_DIR/skills/.system/skill-creator/scripts/quick_validate.py"
if [ -f "$VALIDATOR" ] && python3 -c 'import yaml' 2>/dev/null; then
  if out=$(python3 "$VALIDATOR" "$SRC" 2>&1); then log "valid   $out"; else fail "skill validation: $out"; fi
fi

[ "$FAILED" = 0 ] || { echo "install finished with failures" >&2; exit 1; }

CONFIG=${OUTLINE_MEMORY_CONFIG:-$HOME/.outline-memory.yml}
if [ "$CHECK" = 1 ] && [ "$DRY" = 0 ]; then
  if [ -f "$CONFIG" ]; then
    echo; echo "running: outline-memory check"
    rc=0; "$SRC/scripts/outline-memory" check || rc=$?
    [ "$rc" = 0 ] || { echo "check reported problems (see hints above)"; exit "$rc"; }
  else
    cat <<EOF

next steps:
  1. cp $HERE/config.example.yml $CONFIG   && edit url: (chmod 600 $CONFIG)
  2. (umask 077; printf '%s\n' ol_api_YOUR_KEY > ~/.outline-token)
  3. $SRC/scripts/outline-memory check
then say "create memory of this conversation", or /outlinememory (Claude Code), or \$outlinememory (Codex).
EOF
  fi
fi
