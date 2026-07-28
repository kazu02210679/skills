#!/usr/bin/env bash
#
# codex_resume.sh — feed Codex a follow-up hint when it got stuck.
#
# This is the "Claude steps in with an opinion" step. Claude reads Codex's
# previous report + failing logs, writes a hint file (root cause + concrete
# guidance + a minimal path forward), and calls this script to continue.
#
# Each call lands in a NEW attempt directory under the same <rundir>, so the
# evidence from the attempt being fixed survives. When the loop gives up and
# escalates, every attempt is still on disk to explain what was tried.
#
# Continuation mode is decided BEFORE spending a run:
#   auto   (default) resume the exact session recorded in <rundir>/thread_id
#          when the CLI supports it; otherwise fresh.
#   resume force targeted resume; fails if no thread id was captured.
#   last   resume whatever session the CLI saw most recently. Only correct if
#          nothing else has used Codex in this workdir since — another terminal
#          or agent would silently receive the hint instead.
#   fresh  run a fresh `codex exec` whose prompt carries the previous report
#          and the hint — portable, no session state needed.
#
# Usage:
#   codex_resume.sh <hint_file> <workdir> <rundir> [prev_report]
#
# Env:
#   CODEX_RESUME_MODE   auto|resume|last|fresh  (default: auto)
#   CODEX_MAX_ATTEMPTS  refuse past this many attempts (default 3, 0 = no cap)
#   plus the same overrides as codex_run.sh (CODEX_MODEL, CODEX_SANDBOX,
#   CODEX_EXTRA_ARGS, CODEX_TIMEOUT, CODEX_ALLOWLIST, ...).
#
# Exit codes: same contract as codex_run.sh (0 ok, 2 usage, 3 out of scope,
# 4 metadata tampered, otherwise Codex's own exit code).
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=codex_lib.sh
. "$SCRIPT_DIR/codex_lib.sh"

die() { printf 'codex_resume: %s\n' "$1" >&2; exit 2; }

[ "$#" -ge 3 ] || die "usage: codex_resume.sh <hint_file> <workdir> <rundir> [prev_report]"

HINT="$1"
WORKDIR="$2"
RUNDIR="$3"

command -v codex >/dev/null 2>&1 || die "the 'codex' CLI is not installed or not on PATH."
codex_require_hash || exit 2
codex_require_json_encoder || exit 2
[ -f "$HINT" ]    || die "hint file not found: $HINT"
[ -d "$WORKDIR" ] || die "workdir not found: $WORKDIR"
[ -d "$RUNDIR" ]  || die "run directory not found: $RUNDIR (pass the RUNDIR printed by codex_run.sh)"

WORKDIR_ABS="$(cd -- "$WORKDIR" && pwd)"
git -C "$WORKDIR" rev-parse --is-inside-work-tree >/dev/null 2>&1 \
  || die "$WORKDIR is not a git repository. Resume cannot enforce the frozen scope without Git."
[ -s "$RUNDIR/workdir" ] || die "run directory has no recorded workdir: $RUNDIR/workdir"
RECORDED_WORKDIR="$(cat "$RUNDIR/workdir")"
[ "$WORKDIR_ABS" = "$RECORDED_WORKDIR" ] \
  || die "supplied workdir '$WORKDIR_ABS' does not match this run's recorded workdir '$RECORDED_WORKDIR'"
[ -s "$RUNDIR/base_commit" ] || die "run directory has no frozen base commit: $RUNDIR/base_commit"
BASE_COMMIT="$(tr -d '[:space:]' <"$RUNDIR/base_commit")"
git -C "$WORKDIR" rev-parse --verify --quiet "$BASE_COMMIT^{commit}" >/dev/null 2>&1 \
  || die "frozen base commit does not resolve in the recorded workdir: '$BASE_COMMIT'"

if ! codex_contract_check "$RUNDIR" "$WORKDIR"; then
  printf 'codex_resume: FAIL 窶・the frozen contract is missing or changed.\n' >&2
  exit 4
fi

# --- locate the previous attempt, open the next one -------------------------
last_attempt_number() {
  local d n last=0
  for d in "$RUNDIR"/attempt-*; do
    [ -d "$d" ] || continue
    n="${d##*/attempt-}"
    case "$n" in ''|*[!0-9]*) continue ;; esac
    [ "$n" -gt "$last" ] && last="$n"
  done
  printf '%s\n' "$last"
}

MAX="${CODEX_MAX_ATTEMPTS:-3}"
case "$MAX" in
  ''|*[!0-9]*) die "CODEX_MAX_ATTEMPTS must be a nonnegative integer, got '$MAX'" ;;
esac
while [ "${MAX#0}" != "$MAX" ]; do MAX="${MAX#0}"; done
[ -n "$MAX" ] || MAX=0

LAST_N="$(last_attempt_number)"
[ "$LAST_N" -gt 0 ] || die "no attempt-N directory under $RUNDIR — run codex_run.sh first"

PREV="$RUNDIR/attempt-$LAST_N"
N=$((LAST_N + 1))

# The skill caps the hint loop at three attempts and escalates. Enforce it here
# too: a cap that lives only in prose is one an agent can lose track of, and
# each extra attempt costs a full Codex run.
if [ "$MAX" != "0" ] && [ "$N" -gt "$MAX" ]; then
  die "attempt $N would exceed CODEX_MAX_ATTEMPTS=$MAX. Codex is not converging — stop and escalate to the user with the reports in $RUNDIR, or raise the cap deliberately."
fi

ATTEMPT="$RUNDIR/attempt-$N"
PREV_REPORT="${4:-$PREV/report.md}"

# NOTE: $ATTEMPT is deliberately NOT created yet. Attempts are counted by
# directory, so creating one before the mode checks below have passed would
# leave an empty attempt behind on a usage error and burn a slot off the cap
# without Codex ever running.

# The plan this run belongs to, recorded by codex_run.sh. The integrity check
# is scoped to it so a second agent working a different plan in the same
# repository does not trip this one.
PLAN_DIR="$(cd -- "$(dirname -- "$HINT")" && pwd)"
[ -s "$RUNDIR/plan_dir" ] && PLAN_DIR="$(cat "$RUNDIR/plan_dir")"
PLAN_WATCH=""
case "$PLAN_DIR" in
  "$(cd -- "$WORKDIR" && pwd)/$CODEX_META_DIR"|"$(cd -- "$WORKDIR" && pwd)/$CODEX_META_DIR"/*)
    PLAN_WATCH="$PLAN_DIR" ;;
esac

THREAD_ID=""
[ -f "$RUNDIR/thread_id" ] && THREAD_ID="$(tr -d '[:space:]' <"$RUNDIR/thread_id")"

ALLOWLIST=""
if [ -f "$RUNDIR/allowlist" ]; then ALLOWLIST="$RUNDIR/allowlist"; fi
if [ -n "${CODEX_ALLOWLIST:-}" ] && [ "$CODEX_ALLOWLIST" != "$ALLOWLIST" ]; then
  die "CODEX_ALLOWLIST cannot replace this run's frozen allowlist; use $ALLOWLIST"
fi

CODEX_SANDBOX="${CODEX_SANDBOX:-workspace-write}"
CODEX_TIMEOUT="${CODEX_TIMEOUT:-3600}"
CODEX_RESUME_MODE="${CODEX_RESUME_MODE:-auto}"

TIMEOUT_CMD=()
while IFS= read -r t; do [ -n "$t" ] && TIMEOUT_CMD+=("$t"); done < <(codex_timeout_prefix "$CODEX_TIMEOUT")

run_resume() {
  "${TIMEOUT_CMD[@]}" codex exec "${common[@]}" resume "$THREAD_ID" "$(cat "$HINT")" </dev/null
}

run_last() {
  "${TIMEOUT_CMD[@]}" codex exec "${common[@]}" resume --last "$(cat "$HINT")" </dev/null
}

run_fresh() {
  local prompt
  prompt="You are continuing a task you did not finish. Before doing anything,
re-read your previous report and the failing logs, then apply the guidance below.

## Your previous report
$( [ -f "$PREV_REPORT" ] && cat "$PREV_REPORT" || echo '(none)')

## Guidance from the orchestrator
$(cat "$HINT")

Do not restart from scratch or make large unrequested changes. Make the minimal
change that unblocks the task, re-run the tests, and report what you did."
  "${TIMEOUT_CMD[@]}" codex exec "${common[@]}" "$prompt" </dev/null
}

# --- pick the mode up front -------------------------------------------------
# Deciding by probing the CLI (rather than pattern-matching stderr after a
# failed run) keeps a plain task failure from being misread as "resume is
# unsupported" and silently charged for a second, redundant run.
supports_resume() { codex exec resume --help >/dev/null 2>&1; }

case "$CODEX_RESUME_MODE" in
  fresh) MODE=fresh ;;
  last)  MODE=last ;;
  resume)
    [ -n "$THREAD_ID" ] || die "CODEX_RESUME_MODE=resume but no session id was captured in $RUNDIR/thread_id. Use fresh mode, or last if you are certain nothing else has used Codex here."
    MODE=resume
    ;;
  auto)
    if [ -n "$THREAD_ID" ] && supports_resume; then
      MODE=resume
    else
      MODE=fresh
      if [ -z "$THREAD_ID" ]; then
        printf 'codex_resume: no session id recorded — using fresh mode\n' >&2
      else
        printf 'codex_resume: this Codex CLI has no `exec resume` — using fresh mode\n' >&2
      fi
    fi
    ;;
  *) die "unknown CODEX_RESUME_MODE: '$CODEX_RESUME_MODE' (expected auto|resume|last|fresh)" ;;
esac

# Every check that can reject this call has now run. Reserve the attempt with
# atomic mkdir; a concurrent resume that won the same number makes us rescan.
RESERVATION_COLLISIONS=0
MAX_RESERVATION_COLLISIONS=16
while :; do
  LAST_N="$(last_attempt_number)"
  [ "$LAST_N" -gt 0 ] || die "no prior attempt remains under $RUNDIR"
  N=$((LAST_N + 1))
  if [ "$MAX" != "0" ] && [ "$N" -gt "$MAX" ]; then
    die "attempt $N would exceed CODEX_MAX_ATTEMPTS=$MAX. Codex is not converging 窶・stop and escalate to the user with the reports in $RUNDIR, or raise the cap deliberately."
  fi
  ATTEMPT="$RUNDIR/attempt-$N"
  if mkdir "$ATTEMPT" 2>/dev/null; then break; fi
  [ -d "$ATTEMPT" ] || \
    die "could not reserve $ATTEMPT; the failure was not a directory collision"
  RESERVATION_COLLISIONS=$((RESERVATION_COLLISIONS + 1))
  if [ "$RESERVATION_COLLISIONS" -ge "$MAX_RESERVATION_COLLISIONS" ]; then
    die "could not reserve an attempt after $MAX_RESERVATION_COLLISIONS verified directory collisions"
  fi
done
PREV="$RUNDIR/attempt-$LAST_N"
PREV_REPORT="${4:-$PREV/report.md}"

# Shared options belong to `exec`, so they go between `exec` and the `resume`
# subcommand. Placing them after `resume` makes the CLI reject them.
common=(--cd "$WORKDIR" --sandbox "$CODEX_SANDBOX"
        --output-last-message "$ATTEMPT/report.md" --json)
[ -n "${CODEX_MODEL:-}" ] && common+=(-m "$CODEX_MODEL")
# shellcheck disable=SC2206
[ -n "${CODEX_EXTRA_ARGS:-}" ] && common+=(${CODEX_EXTRA_ARGS})

printf 'codex_resume: continuing from attempt-%s\n  hint    : %s\n  mode    : %s%s\n  attempt : %s (cap %s)\n  scope   : %s\n' \
  "$LAST_N" "$HINT" "$MODE" "${THREAD_ID:+ [$THREAD_ID]}" "$ATTEMPT" "$MAX" "${ALLOWLIST:-(none)}" >&2

META_BEFORE=""
[ -n "$PLAN_WATCH" ] && META_BEFORE="$(codex_meta_fingerprint "$PLAN_WATCH")"

set +e
case "$MODE" in
  fresh)  run_fresh  >"$ATTEMPT/events.jsonl" 2>"$ATTEMPT/stderr.log" ;;
  last)   run_last   >"$ATTEMPT/events.jsonl" 2>"$ATTEMPT/stderr.log" ;;
  resume) run_resume >"$ATTEMPT/events.jsonl" 2>"$ATTEMPT/stderr.log" ;;
esac
RC=$?
set -e
[ "$RC" -eq 124 ] && printf 'codex_resume: Codex hit the %ss timeout\n' "$CODEX_TIMEOUT" >&2

[ -f "$ATTEMPT/report.md" ] || printf '(no final message captured; see stderr.log)\n' >"$ATTEMPT/report.md"

NEW_ID="$(codex_thread_id "$ATTEMPT/events.jsonl")"
[ -n "$NEW_ID" ] && printf '%s\n' "$NEW_ID" >"$RUNDIR/thread_id"

META_OK=true
if [ -n "$PLAN_WATCH" ] && [ "$META_BEFORE" != "$(codex_meta_fingerprint "$PLAN_WATCH")" ]; then
  META_OK=false
  printf 'codex_resume: FAIL — Codex modified the plan directory during the run:\n  %s\n' "$PLAN_DIR" >&2
fi

CONTRACT_OK=true
if ! codex_contract_check "$RUNDIR" "$WORKDIR"; then
  CONTRACT_OK=false
  printf 'codex_resume: FAIL 窶・the frozen contract changed during the resume.\n' >&2
fi

# --- scope gate -------------------------------------------------------------
SCOPE_RC=0
if [ "$CONTRACT_OK" = "true" ] && [ -n "$ALLOWLIST" ]; then
  set +e
  "$SCRIPT_DIR/codex_scope_check.sh" "$ALLOWLIST" "$WORKDIR" "$BASE_COMMIT" \
    >"$ATTEMPT/scope.txt" 2>&1
  SCOPE_RC=$?
  set -e
  cat "$ATTEMPT/scope.txt" >&2
fi

SCOPE_OK=false
[ "$SCOPE_RC" -eq 0 ] && SCOPE_OK=true
codex_write_json "$ATTEMPT/meta.json" \
  hint string "$HINT" \
  workdir string "$WORKDIR" \
  rundir string "$RUNDIR" \
  attempt integer "$N" \
  resumed_from integer "$LAST_N" \
  mode string "$MODE" \
  thread_id string "$THREAD_ID" \
  base_commit string "$BASE_COMMIT" \
  allowlist string "${ALLOWLIST:-}" \
  meta_intact boolean "$META_OK" \
  contract_intact boolean "$CONTRACT_OK" \
  scope_ok boolean "$SCOPE_OK" \
  sandbox string "$CODEX_SANDBOX" \
  model string "${CODEX_MODEL:-default}" \
  exit_code integer "$RC" \
  finished_at string "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  || die "could not write JSON resume metadata"

printf 'codex_resume: done (exit=%s)\n  REPORT: %s\n  EVENTS: %s\n  META  : %s\n' \
  "$RC" "$ATTEMPT/report.md" "$ATTEMPT/events.jsonl" "$ATTEMPT/meta.json" >&2

[ "$META_OK" = "true" ] && [ "$CONTRACT_OK" = "true" ] || exit 4
if [ "$RC" -eq 0 ] && [ "$SCOPE_RC" -ne 0 ]; then
  exit 3
fi
exit "$RC"
