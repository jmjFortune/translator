#!/usr/bin/env bash
# 为单个任务创建隔离 worktree，并可选地直接启动某个 agent CLI。
# 用法: scripts/agent.sh <task-name> <codex|gemini|opencode> ["prompt"]
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/agent.sh <task-name> <codex|gemini|opencode> ["prompt"]

Creates ../Translator-wt-<task> on branch agent/<agent>/<task>.
With a prompt, runs the matching CLI inside that worktree.
EOF
}

if [ $# -lt 2 ]; then usage; exit 1; fi

TASK="$1"
AGENT="$2"
shift 2

ROOT="$(git rev-parse --show-toplevel)"
SLUG="$(printf '%s' "$TASK" | tr '[:upper:]' '[:lower:]' \
  | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//' | cut -c1-40)"

if [ -z "$SLUG" ]; then
  echo "task name must contain at least one letter or digit" >&2
  exit 1
fi

case "$AGENT" in
  codex|gemini|opencode) ;;
  *) echo "unknown agent: $AGENT (expected codex|gemini|opencode)" >&2; exit 1 ;;
esac

BRANCH="agent/$AGENT/$SLUG"
WT="$(dirname "$ROOT")/$(basename "$ROOT")-wt-$SLUG"

if [ -d "$WT" ]; then
  echo "worktree already exists: $WT" >&2
  exit 1
fi

git -C "$ROOT" worktree add -B "$BRANCH" "$WT" HEAD

printf 'worktree: %s\nbranch:   %s\n' "$WT" "$BRANCH"

if [ $# -eq 0 ]; then
  printf '\ncd "%s" and run your agent.\n' "$WT"
  exit 0
fi

command -v "$AGENT" >/dev/null 2>&1 || {
  echo "$AGENT CLI not found in PATH" >&2
  exit 1
}

PROMPT="$*"
cd "$WT"

case "$AGENT" in
  codex)    exec codex exec "$PROMPT" ;;
  gemini)   exec gemini -p "$PROMPT" ;;
  opencode) exec opencode run "$PROMPT" ;;
esac
