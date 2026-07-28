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

# Install one cleanup path before any temporary allocation. Each path is set
# only after this process creates it; LOCK_HELD prevents removing another
# process's pre-existing lock after a failed reservation.
LOCK_DIR=""; LOCK_HELD=0
PRODUCT_CAPTURE=""
TEST_OUT=""; MESSAGE_FILE=""; INDEX_DIR=""; INDEX_FILE=""
cleanup() {
  local path
  for path in "$PRODUCT_CAPTURE" "$TEST_OUT" "$MESSAGE_FILE" "$INDEX_FILE"; do
    if [ -n "$path" ]; then
      rm -f -- "$path" 2>/dev/null || true
    fi
  done
  [ -z "$INDEX_DIR" ] || rmdir "$INDEX_DIR" 2>/dev/null || true
  if [ "$LOCK_HELD" = "1" ] && [ -n "$LOCK_DIR" ]; then
    rmdir "$LOCK_DIR" 2>/dev/null || true
  fi
}
trap cleanup EXIT

[ -d "$TASKDIR" ] || die "task directory not found: $TASKDIR"
[ -d "$WORKDIR" ] || die "workdir not found: $WORKDIR"
[ -d "$RUNDIR" ] || die "run directory not found: $RUNDIR"
git -C "$WORKDIR" rev-parse --is-inside-work-tree >/dev/null 2>&1 || die "not a git repository: $WORKDIR"
codex_require_hash || exit 2

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
[ -s "$RUNDIR/allowlist_source" ] || contract_failure "the frozen contract does not record where its allowlist came from"
[ -f "$RUNDIR/task.md" ] || contract_failure "the frozen contract has no task packet"
[ -f "$RUNDIR/plan-id" ] || contract_failure "the frozen contract has no plan identity"
[ -f "$RUNDIR/base_commit" ] || contract_failure "the frozen contract has no baseline"

BASE_COMMIT="$(tr -d '[:space:]' <"$RUNDIR/base_commit")"
[ -n "$BASE_COMMIT" ] || contract_failure "the frozen baseline is empty"
git -C "$WORKDIR_ABS" rev-parse --verify --quiet "$BASE_COMMIT^{commit}" >/dev/null 2>&1 || \
  contract_failure "the frozen baseline does not resolve in this worktree"
head_gate() {
  local current
  current="$(git -C "$WORKDIR_ABS" rev-parse --verify --quiet 'HEAD^{commit}' 2>/dev/null || true)"
  [ -n "$current" ] || die "HEAD does not resolve to a commit; refusing publication"
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
git -C "$WORKDIR_ABS" diff --cached --quiet || die "the Git index already contains staged changes; refusing to mix unrelated work into this task commit"

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
LOCK_HELD=1

# A lock waits for nothing: repeat the baseline check after acquiring it so a
# gate that started while another task committed cannot judge a partial diff.
head_gate

# Retain every verdict input in parent-shell memory before executing arbitrary
# test commands. The allowlist is read exactly once: a sentinel preserves all
# trailing newlines in Bash's command substitution, its captured bytes are
# authenticated against the anchored manifest, and those same bytes are parsed.
# Child test shells can rewrite pathnames, but cannot mutate these arrays,
# digests, or strings.
CONTRACT_ANCHOR="$(codex_contract_anchor "$WORKDIR_ABS" "$RUNDIR")" || \
  contract_failure "the trusted frozen contract anchor cannot be resolved"
ALLOWLIST_EXPECTED_DIGEST=""
while IFS=' ' read -r kind hash rel extra || [ -n "${kind:-}" ]; do
  if [ "$kind" = "F" ] && [ "$rel" = "allowlist" ] && [ -z "${extra:-}" ]; then
    ALLOWLIST_EXPECTED_DIGEST="$hash"
    break
  fi
done <"$CONTRACT_ANCHOR"
[ -n "$ALLOWLIST_EXPECTED_DIGEST" ] || \
  contract_failure "the trusted frozen contract has no allowlist digest"
ALLOWLIST_SENTINEL=$'\034'
ALLOWLIST_BYTES="$(cat -- "$RUNDIR/allowlist"; printf '%s' "$ALLOWLIST_SENTINEL")" || \
  contract_failure "could not capture the frozen allowlist"
case "$ALLOWLIST_BYTES" in
  *"$ALLOWLIST_SENTINEL") ALLOWLIST_BYTES="${ALLOWLIST_BYTES%?}" ;;
  *) contract_failure "could not preserve the frozen allowlist bytes" ;;
esac
ALLOWLIST_CAPTURE_DIGEST="$(printf '%s' "$ALLOWLIST_BYTES" | "${CODEX_HASH[@]}" | cut -d' ' -f1)" || \
  contract_failure "could not authenticate the captured allowlist"
[ "$ALLOWLIST_CAPTURE_DIGEST" = "$ALLOWLIST_EXPECTED_DIGEST" ] || \
  contract_failure "the captured allowlist does not match the trusted frozen contract"

CONTRACT_DIGEST="$(codex_hash_file "$RUNDIR/contract.sha256")" || \
  contract_failure "could not retain the frozen contract digest"
ALLOWLIST_DIGEST="$ALLOWLIST_EXPECTED_DIGEST"
TASK_DIGEST="$(codex_hash_file "$RUNDIR/task.md")" || \
  contract_failure "could not retain the frozen task digest"
PLAN_ID_DIGEST="$(codex_hash_file "$RUNDIR/plan-id")" || \
  contract_failure "could not retain the frozen plan identity digest"
TEST_DIGEST="$(codex_hash_file "$RUNDIR/test")" || \
  contract_failure "could not retain the frozen test digest"
RECORDED_TEST_SOURCE="$( [ -f "$RUNDIR/test_source" ] && cat "$RUNDIR/test_source" || true)"
RECORDED_ALLOWLIST_SOURCE="$(cat "$RUNDIR/allowlist_source")" || \
  contract_failure "could not retain the frozen allowlist origin"
[ -n "$RECORDED_ALLOWLIST_SOURCE" ] || contract_failure "the frozen allowlist origin is empty"
PLAN_FINGERPRINT="$(codex_meta_fingerprint "$TASKDIR_ABS")" || \
  contract_failure "could not retain the live plan fingerprint"
ALLOWLIST_PATTERNS=()
codex_load_allowlist_text "$ALLOWLIST_BYTES" ALLOWLIST_PATTERNS
[ "${#ALLOWLIST_PATTERNS[@]}" -gt 0 ] || contract_failure "the frozen allowlist has no patterns"

PLAN_ID="$(tr -d '[:space:]' <"$RUNDIR/plan-id")"
[ -n "$PLAN_ID" ] || contract_failure "the frozen plan identity is empty"

# Live plan files must still be byte-identical to their frozen counterparts;
# this also checks whether a per-task test appeared/disappeared after the run.
plan_drift_gate() {
  local live_test
  local -a drift=()
  [ "$(codex_hash_file "$TASK_MD")" = "$TASK_DIGEST" ] || drift+=("$TASK_ID.md")
  # Compare the allowlist where the run actually read it. Assuming
  # `T<N>.allowlist` reported drift on every CODEX_ALLOWLIST run — a supported
  # control — and left that task permanently uncommittable, with a diagnostic
  # that blamed a plan edit nobody had made.
  [ "$(codex_hash_file "$RECORDED_ALLOWLIST_SOURCE")" = "$ALLOWLIST_DIGEST" ] ||
    drift+=("$RECORDED_ALLOWLIST_SOURCE")
  [ "$(codex_hash_file "$TASKDIR_ABS/plan-id")" = "$PLAN_ID_DIGEST" ] || drift+=("plan-id")
  live_test="$(codex_test_file "$TASKDIR_ABS" "$TASK_ID")"
  if [ -n "$live_test" ]; then
    live_test="$(cd -- "$(dirname -- "$live_test")" && pwd)/$(basename -- "$live_test")"
  fi
  [ "$live_test" = "$RECORDED_TEST_SOURCE" ] || drift+=("test commands")
  [ "$(codex_hash_file "$live_test")" = "$TEST_DIGEST" ] || drift+=("test commands")
  [ "$(codex_meta_fingerprint "$TASKDIR_ABS")" = "$PLAN_FINGERPRINT" ] || drift+=("plan directory")
  if [ "${#drift[@]}" -gt 0 ]; then
    contract_failure "the plan changed since this task was run: ${drift[*]}"
  fi
}
plan_drift_gate

contract_gate() {
  [ "$(codex_hash_file "$RUNDIR/contract.sha256")" = "$CONTRACT_DIGEST" ] || \
    contract_failure "the frozen contract manifest changed while tests were running"
  [ "$(codex_hash_file "$RUNDIR/allowlist")" = "$ALLOWLIST_DIGEST" ] || \
    contract_failure "the frozen allowlist changed while tests were running"
  if ! codex_contract_check "$RUNDIR" "$WORKDIR_ABS"; then
    contract_failure "the frozen contract changed while tests were running"
  fi
}

collect_product_paths() {
  local output_name="$1"
  local -n output="$output_name"
  output=()
  PRODUCT_CAPTURE="$(mktemp)" || die "could not create a product-path capture"
  if ! codex_dirty_product0 "$WORKDIR_ABS" HEAD >"$PRODUCT_CAPTURE"; then
    die "could not reliably determine changed product files"
  fi
  mapfile -d '' -t output <"$PRODUCT_CAPTURE"
  rm -f -- "$PRODUCT_CAPTURE" || die "could not remove the product-path capture before tests"
  PRODUCT_CAPTURE=""
}

PRODUCT_PATHS=()
collect_product_paths PRODUCT_PATHS
if [ "${#PRODUCT_PATHS[@]}" -eq 0 ]; then
  say "$TASK_ID changed no product files — refusing to record it as done"
  exit 1
fi

scope_paths_gate() {
  local when="$1" path
  local -a violations=()
  shift
  for path in "$@"; do
    codex_path_allowed "$path" "${ALLOWLIST_PATTERNS[@]}" || violations+=("$path")
  done
  if [ "${#violations[@]}" -gt 0 ]; then
    printf 'codex_commit: out-of-scope product path(s) (%s):\n' "$when" >&2
    printf '  %s\n' "${violations[@]}" >&2
    say "$TASK_ID is out of scope ($when) — not committing"
    exit 3
  fi
}
scope_paths_gate "before tests" "${PRODUCT_PATHS[@]}"

# Freeze exactly the candidate tree before tests. The private index starts at
# BASE_COMMIT and receives only literal collected product paths plus the active
# plan. This tree is the sole source of the commit eventually published.
STAGE_PATHS=("${PRODUCT_PATHS[@]}")
case "$TASKDIR_ABS" in
  "$WORKDIR_ABS"/*) STAGE_PATHS+=("${TASKDIR_ABS#"$WORKDIR_ABS"/}") ;;
  *) say "note: $TASKDIR_ABS is outside the repository; the plan will not be committed with the task" ;;
esac
build_candidate_tree() {
  local output_name="$1" phase="$2"
  local -n output="$output_name"
  INDEX_DIR="$(mktemp -d)" || die "could not create the $phase isolated Git-index directory"
  INDEX_FILE="$INDEX_DIR/index"
  GIT_INDEX_FILE="$INDEX_FILE" git -C "$WORKDIR_ABS" read-tree "$BASE_COMMIT" || \
    die "could not initialize the $phase isolated Git index from the frozen baseline"
  GIT_LITERAL_PATHSPECS=1 GIT_INDEX_FILE="$INDEX_FILE" \
    git -C "$WORKDIR_ABS" add -A -- "${STAGE_PATHS[@]}" || \
    die "could not add the literal task paths to the $phase isolated Git index"
  output="$(GIT_INDEX_FILE="$INDEX_FILE" git -C "$WORKDIR_ABS" write-tree)" || \
    die "could not write the $phase candidate tree"
  rm -f -- "$INDEX_FILE" || die "could not remove the $phase isolated Git index"
  INDEX_FILE=""
  rmdir "$INDEX_DIR" || die "could not remove the $phase isolated Git-index directory"
  INDEX_DIR=""
}

TREE=""
build_candidate_tree TREE "pre-test"

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

# Tests are adversarial workspace code. Re-establish the retained contract and
# live-plan digests, then require the literal product set and every selected
# worktree blob to match the immutable tree frozen before tests.
contract_gate
plan_drift_gate
head_gate
PRODUCT_PATHS_AFTER=()
collect_product_paths PRODUCT_PATHS_AFTER
PATH_SET_CHANGED=0
if [ "${#PRODUCT_PATHS[@]}" -ne "${#PRODUCT_PATHS_AFTER[@]}" ]; then
  PATH_SET_CHANGED=1
else
  for ((i = 0; i < ${#PRODUCT_PATHS[@]}; i++)); do
    if [ "${PRODUCT_PATHS[$i]}" != "${PRODUCT_PATHS_AFTER[$i]}" ]; then
      PATH_SET_CHANGED=1
      break
    fi
  done
fi
if [ "$PATH_SET_CHANGED" -eq 1 ]; then
  scope_paths_gate "after tests" "${PRODUCT_PATHS_AFTER[@]}"
  die "product path set changed after candidate freeze; refusing to publish"
fi
TREE_AFTER=""
build_candidate_tree TREE_AFTER "post-test"
[ "$TREE_AFTER" = "$TREE" ] || \
  die "candidate tree changed after tests; refusing to publish"

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
cat >"$MESSAGE_FILE" <<EOF
$SUBJECT

Codex-Plan: $PLAN_ID
Codex-Task: $TASK_ID
Codex-Tests: ${#commands[@]} command(s) passed
EOF

CANDIDATE="$(git -C "$WORKDIR_ABS" commit-tree "$TREE" -p "$BASE_COMMIT" <"$MESSAGE_FILE")" || \
  die "could not create the candidate task commit"

# Test-only seam: a real competing writer can change refs after the candidate
# exists but before the CAS. Normal runs leave this unset.
if [ -n "${CODEX_COMMIT_TEST_BEFORE_PUBLISH:-}" ]; then
  [ -x "$CODEX_COMMIT_TEST_BEFORE_PUBLISH" ] || die "CODEX_COMMIT_TEST_BEFORE_PUBLISH is not an executable file"
  "$CODEX_COMMIT_TEST_BEFORE_PUBLISH" || die "pre-publication test hook failed"
fi

# A branch ref becoming a symref is itself a publication conflict. --no-deref
# below prevents redirection even if a non-cooperating writer races this check;
# this check ensures a symref already installed before the CAS is never replaced
# while being reported as a successful task publication.
if git -C "$WORKDIR_ABS" symbolic-ref -q "$HEAD_REF" >/dev/null 2>&1; then
  say "publication conflict: $HEAD_REF became a symbolic ref; task commit was not published"
  exit 5
fi

# HEAD_REF was pinned while HEAD still resolved to BASE_COMMIT. Publishing by
# this named ref (rather than by HEAD) prevents a later symbolic-HEAD repoint
# from redirecting this task's commit to another branch.
set +e
git -C "$WORKDIR_ABS" update-ref --no-deref "$HEAD_REF" "$CANDIDATE" "$BASE_COMMIT"
PUBLISH_RC=$?
set -e
if [ "$PUBLISH_RC" -ne 0 ]; then
  # `commit-tree` has already created an object. Without a ref it is harmless
  # and may remain unreachable until Git's normal garbage collection reclaims it.
  say "publication conflict: $HEAD_REF changed after candidate creation; task commit was not published"
  exit 5
fi

# Only now, with the commit published, bring the real index up to the tree that
# was published. Staging before the CAS left the index dirty on every
# publication conflict, and the next attempt then refused itself with "the Git
# index already contains staged changes" — blaming the operator for this gate's
# own residue. Only selected task paths are added; unrelated entries staged by
# a test or a concurrent writer remain visible.
if ! GIT_LITERAL_PATHSPECS=1 git -C "$WORKDIR_ABS" add -A -- "${STAGE_PATHS[@]}"; then
  # The task IS committed; this is cosmetic bookkeeping, so do not report the
  # publication as failed. Say exactly what is left to do.
  say "warning: $TASK_ID was published, but the index could not be refreshed. Run 'git reset' in $WORKDIR_ABS before the next task."
fi
printf '%s\n' "$HEAD_REF" >"$RUNDIR/commit.ref" || contract_failure "could not write commit target evidence"
SHA="$(git -C "$WORKDIR_ABS" rev-parse --short "$CANDIDATE")"
say "$TASK_ID committed $SHA to $HEAD_REF (${#commands[@]} test command(s) green)"
printf '%s\n' "$SHA"
