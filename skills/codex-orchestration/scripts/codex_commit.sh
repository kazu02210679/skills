#!/usr/bin/env bash
# Close one frozen Codex task only when its scope, contract and tests hold.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=codex_lib.sh
. "$SCRIPT_DIR/codex_lib.sh"

die() { printf 'codex_commit: %s\n' "$1" >&2; exit 2; }
say() { printf 'codex_commit: %s\n' "$1" >&2; }
contract_failure() { say "$1"; exit 6; }

[ "$#" -eq 4 ] || die "usage: codex_commit.sh <taskdir> <task_id> <workdir> <rundir>"
TASKDIR="$1"; TASK_ID="$2"; WORKDIR="$3"; RUNDIR="$4"

[ -d "$TASKDIR" ] || die "task directory not found: $TASKDIR"
[ -d "$WORKDIR" ] || die "workdir not found: $WORKDIR"
[ -d "$RUNDIR" ] || die "run directory not found: $RUNDIR"
git -C "$WORKDIR" rev-parse --is-inside-work-tree >/dev/null 2>&1 || die "not a git repository: $WORKDIR"
codex_require_hash || exit 2
git -C "$WORKDIR" diff --cached --quiet || die "the Git index already contains staged changes; refusing to mix unrelated work into this task commit"

TASKDIR_ABS="$(cd -- "$TASKDIR" && pwd)"
WORKDIR_ABS="$(cd -- "$WORKDIR" && pwd)"
TASK_MD="$TASKDIR_ABS/$TASK_ID.md"
[ -f "$TASK_MD" ] || die "task packet not found: $TASK_MD"

# The run directory is workspace-writable. Its contents become trusted only
# after they match the manifest anchored under Git metadata by codex_run.sh.
if ! codex_contract_check "$RUNDIR" "$WORKDIR_ABS"; then
  contract_failure "the frozen contract is missing or changed; refusing to commit"
fi
[ -s "$RUNDIR/plan_dir" ] || contract_failure "the frozen contract has no plan identity"
RECORDED_PLAN="$(cat "$RUNDIR/plan_dir")"
[ "$RECORDED_PLAN" = "$TASKDIR_ABS" ] || contract_failure "the supplied plan is not this run's frozen plan identity"
[ -f "$RUNDIR/allowlist" ] || contract_failure "the frozen contract has no allowlist"
[ -f "$RUNDIR/task.md" ] || contract_failure "the frozen contract has no task packet"
[ -f "$RUNDIR/plan-id" ] || contract_failure "the frozen contract has no plan identity"
[ -f "$RUNDIR/base_commit" ] || contract_failure "the frozen contract has no baseline"

BASE_COMMIT="$(tr -d '[:space:]' <"$RUNDIR/base_commit")"
[ -n "$BASE_COMMIT" ] || contract_failure "the frozen baseline is empty"
git -C "$WORKDIR_ABS" rev-parse --verify --quiet "$BASE_COMMIT^{commit}" >/dev/null 2>&1 || \
  contract_failure "the frozen baseline does not resolve in this worktree"
head_gate() {
  local current
  current="$(git -C "$WORKDIR_ABS" rev-parse HEAD)"
  [ "$current" = "$BASE_COMMIT" ] || {
    say "HEAD moved during $TASK_ID: expected $BASE_COMMIT, found $current"
    exit 5
  }
}
head_gate

# A CAS publication needs a concrete branch ref. `git commit` updates whatever
# HEAD points at after it has prepared the commit, which leaves a final race;
# detached or otherwise unresolved symbolic HEAD has no safe ref to compare.
HEAD_REF="$(git -C "$WORKDIR_ABS" symbolic-ref -q HEAD)" || \
  die "HEAD is detached or has no resolvable symbolic ref; refusing atomic publication"
git -C "$WORKDIR_ABS" rev-parse --verify --quiet "$HEAD_REF^{commit}" >/dev/null 2>&1 || \
  die "symbolic HEAD ref does not resolve to a commit: $HEAD_REF"

# Serialize cooperating commit gates. A stale lock is deliberately an error:
# guessing whether another gate completed would make a clean verdict unsafe.
LOCK_DIR="$(git -C "$WORKDIR_ABS" rev-parse --git-path codex-orchestration-commit.lock)" || die "could not locate Git metadata"
case "$LOCK_DIR" in
  /*|[A-Za-z]:/*) ;;
  *) LOCK_DIR="$WORKDIR_ABS/$LOCK_DIR" ;;
esac
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  die "another codex commit gate is active (or left a stale lock): $LOCK_DIR"
fi
trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT

# A lock waits for nothing: repeat the baseline check after acquiring it so a
# gate that started while another task committed cannot judge a partial diff.
head_gate

ALLOWLIST="$RUNDIR/allowlist"
PLAN_ID="$(tr -d '[:space:]' <"$RUNDIR/plan-id")"
[ -n "$PLAN_ID" ] || contract_failure "the frozen plan identity is empty"

# Live plan files must still be byte-identical to their frozen counterparts;
# this also checks whether a per-task test appeared/disappeared after the run.
drift=()
[ "$(codex_hash_file "$TASK_MD")" = "$(codex_hash_file "$RUNDIR/task.md")" ] || drift+=("$TASK_ID.md")
[ -f "$TASKDIR_ABS/$TASK_ID.allowlist" ] && [ "$(codex_hash_file "$TASKDIR_ABS/$TASK_ID.allowlist")" = "$(codex_hash_file "$ALLOWLIST")" ] || drift+=("$TASK_ID.allowlist")
[ "$(codex_hash_file "$TASKDIR_ABS/plan-id")" = "$(codex_hash_file "$RUNDIR/plan-id")" ] || drift+=("plan-id")
LIVE_TEST="$(codex_test_file "$TASKDIR_ABS" "$TASK_ID")"
RECORDED_TEST_SOURCE="$( [ -f "$RUNDIR/test_source" ] && cat "$RUNDIR/test_source" || true)"
if [ -n "$LIVE_TEST" ]; then LIVE_TEST="$(cd -- "$(dirname -- "$LIVE_TEST")" && pwd)/$(basename -- "$LIVE_TEST")"; fi
[ "$LIVE_TEST" = "$RECORDED_TEST_SOURCE" ] || drift+=("test commands")
[ "$(codex_hash_file "$LIVE_TEST")" = "$(codex_hash_file "$RUNDIR/test")" ] || drift+=("test commands")
if [ "${#drift[@]}" -gt 0 ]; then
  contract_failure "the plan changed since this task was run: ${drift[*]}"
fi

collect_product() {
  local output="$1"
  if ! codex_dirty_product0 "$WORKDIR_ABS" HEAD >"$output"; then
    die "could not reliably determine changed product files"
  fi
}

PRODUCT_LIST="$(mktemp)" || die "could not create a temporary file"
trap 'rm -f "$PRODUCT_LIST"; rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT
collect_product "$PRODUCT_LIST"
if [ ! -s "$PRODUCT_LIST" ]; then
  say "$TASK_ID changed no product files — refusing to record it as done"
  exit 1
fi

scope_gate() {
  local when="$1" rc
  set +e
  "$SCRIPT_DIR/codex_scope_check.sh" "$ALLOWLIST" "$WORKDIR_ABS" "$BASE_COMMIT" >&2
  rc=$?
  set -e
  case "$rc" in
    0) return 0 ;;
    1) say "$TASK_ID is out of scope ($when) — not committing"; exit 3 ;;
    *) die "scope verdict is indeterminate ($when); refusing to commit" ;;
  esac
}
scope_gate "before tests"

commands=()
if [ -f "$RUNDIR/test" ]; then
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line%%#*}"
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    [ -n "$line" ] && commands+=("$line")
  done <"$RUNDIR/test"
fi
if [ "${#commands[@]}" -eq 0 ] && [ "${CODEX_ALLOW_NO_TESTS:-0}" != "1" ]; then
  die "no test commands for $TASK_ID. A commit gate with no tests is not a gate; add one and re-run, or set CODEX_ALLOW_NO_TESTS=1 deliberately."
fi

LOG="$RUNDIR/commit.log"
: >"$LOG" || contract_failure "could not write commit evidence"
record() { printf '%s\n' "$1" | tee -a "$LOG" >&2; }
CODEX_TEST_TIMEOUT="${CODEX_TEST_TIMEOUT:-900}"
TIMEOUT_CMD=()
while IFS= read -r token; do [ -n "$token" ] && TIMEOUT_CMD+=("$token"); done < <(codex_timeout_prefix "$CODEX_TEST_TIMEOUT")
TEST_OUT="$(mktemp)" || die "could not create a test-output file"
MESSAGE_FILE="$(mktemp)" || die "could not create a commit-message file"
trap 'rm -f "$PRODUCT_LIST" "$TEST_OUT" "$MESSAGE_FILE"; rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT
for command in "${commands[@]}"; do
  record "--- $command"
  set +e
  (cd -- "$WORKDIR_ABS" && "${TIMEOUT_CMD[@]}" bash -c "$command") >"$TEST_OUT" 2>&1 </dev/null
  rc=$?
  set -e
  cat "$TEST_OUT" >>"$LOG"
  tail -n 40 "$TEST_OUT" >&2
  if [ "$rc" -ne 0 ]; then
    [ "$rc" -eq 124 ] && record "TIMED OUT after ${CODEX_TEST_TIMEOUT}s: $command"
    record "FAILED (exit $rc): $command"
    say "test gate failed for $TASK_ID — not committing. Full output: $LOG"
    exit 1
  fi
done

scope_gate "after tests"
head_gate
collect_product "$PRODUCT_LIST"
mapfile -d '' -t stage <"$PRODUCT_LIST"
[ "${#stage[@]}" -gt 0 ] || { say "$TASK_ID changed no product files after tests"; exit 1; }
case "$TASKDIR_ABS" in
  "$WORKDIR_ABS"/*) stage+=("${TASKDIR_ABS#"$WORKDIR_ABS"/}") ;;
  *) say "note: $TASKDIR_ABS is outside the repository; the plan will not be committed with the task" ;;
esac

SUBJECT="${CODEX_COMMIT_MESSAGE:-}"
if [ -z "$SUBJECT" ]; then
  SUBJECT="$(grep -m1 '^# ' "$TASK_MD" 2>/dev/null | sed 's/^# *//' || true)"
  [ -n "$SUBJECT" ] || SUBJECT="$TASK_ID"
fi
[ -n "$SUBJECT" ] || die "commit subject is empty"
SUBJECT_WITHOUT_CONTROLS="$(printf '%s' "$SUBJECT" | LC_ALL=C tr -d '[:cntrl:]')"
if [ "$SUBJECT_WITHOUT_CONTROLS" != "$SUBJECT" ]; then
  die "CODEX_COMMIT_MESSAGE must not contain control characters"
fi
head_gate
git -C "$WORKDIR_ABS" add -A -- "${stage[@]}"
head_gate
CURRENT_REF="$(git -C "$WORKDIR_ABS" symbolic-ref -q HEAD)" || \
  die "HEAD is detached or has no resolvable symbolic ref; refusing atomic publication"
[ "$CURRENT_REF" = "$HEAD_REF" ] || {
  say "publication conflict: symbolic HEAD changed from $HEAD_REF to $CURRENT_REF"
  exit 5
}
REF_HEAD="$(git -C "$WORKDIR_ABS" rev-parse --verify --quiet "$HEAD_REF^{commit}" 2>/dev/null || true)"
[ "$REF_HEAD" = "$BASE_COMMIT" ] || {
  say "publication conflict: $HEAD_REF moved from $BASE_COMMIT to ${REF_HEAD:-unresolved}"
  exit 5
}
cat >"$MESSAGE_FILE" <<EOF
$SUBJECT

Codex-Plan: $PLAN_ID
Codex-Task: $TASK_ID
Codex-Tests: ${#commands[@]} command(s) passed
EOF
TREE="$(git -C "$WORKDIR_ABS" write-tree)" || die "could not write the staged tree for publication"
CANDIDATE="$(git -C "$WORKDIR_ABS" commit-tree "$TREE" -p "$BASE_COMMIT" <"$MESSAGE_FILE")" || \
  die "could not create the candidate task commit"

# Test-only seam: a real competing commit can advance the branch after the
# candidate exists but before the CAS. Normal runs leave this unset.
if [ -n "${CODEX_COMMIT_TEST_BEFORE_PUBLISH:-}" ]; then
  [ -x "$CODEX_COMMIT_TEST_BEFORE_PUBLISH" ] || die "CODEX_COMMIT_TEST_BEFORE_PUBLISH is not an executable file"
  "$CODEX_COMMIT_TEST_BEFORE_PUBLISH" || die "pre-publication test hook failed"
fi

set +e
git -C "$WORKDIR_ABS" update-ref "$HEAD_REF" "$CANDIDATE" "$BASE_COMMIT"
PUBLISH_RC=$?
set -e
if [ "$PUBLISH_RC" -ne 0 ]; then
  say "publication conflict: $HEAD_REF changed after candidate creation; task commit was not published"
  exit 5
fi
SHA="$(git -C "$WORKDIR_ABS" rev-parse --short "$CANDIDATE")"
say "$TASK_ID committed as $SHA (${#commands[@]} test command(s) green)"
printf '%s\n' "$SHA"
