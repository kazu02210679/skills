#!/usr/bin/env bash
# codex_run.sh / codex_resume.sh — preflight, prompt assembly, CLI invocation,
# attempt isolation, and the metadata integrity check.
set -uo pipefail
. "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

# run_with_deadline <output-file> <command...>
# Avoid relying on Git for Windows `timeout` process-group behavior while
# pressure-testing the old unbounded reservation loop.
run_with_deadline() {
  local output_file="$1" pid i rc
  shift
  "$@" >"$output_file" 2>&1 & pid=$!
  for i in $(seq 1 300); do
    if ! kill -0 "$pid" 2>/dev/null; then
      wait "$pid"
      return $?
    fi
    sleep 0.01
  done
  kill "$pid" 2>/dev/null || true
  wait "$pid" 2>/dev/null
  rc=$?
  [ "$rc" -eq 0 ] && rc=124
  return "$rc"
}

echo "== git preflight =="
R="$(new_repo run1)"; P="$(new_plan "$R" auth)"
git -C "$R" checkout -q main
out=$("$S/codex_run.sh" "$P/T1.md" "$R" 2>&1); rc=$?
check "refuses the default branch" "$rc" "2"
has "says which branch" "$out" "default branch"
git -C "$R" checkout -q work

R="$(new_repo run1trunk)"; P="$(new_plan "$R" auth)"
git -C "$R" checkout -q main
git -C "$R" branch -m trunk
git -C "$R" config init.defaultBranch trunk
out=$("$S/codex_run.sh" "$P/T1.md" "$R" 2>&1); rc=$?
check "refuses a conventional trunk default branch" "$rc" "2"
has "identifies trunk as the default branch" "$out" "default branch ('trunk')"

R="$TMPROOT/run1unknown"
mkdir -p "$R/src"
git -C "$R" init -q -b release
git -C "$R" config user.email t@t
git -C "$R" config user.name t
git -C "$R" config init.defaultBranch missing-default
echo base >"$R/src/a.py"
git -C "$R" add -A
git -C "$R" commit -qm init
P="$(new_plan "$R" auth)"
LOG="$TMPROOT/unknown-default-argv"; : >"$LOG"
out=$(FAKE_CODEX_LOG="$LOG" "$S/codex_run.sh" "$P/T1.md" "$R" 2>&1); rc=$?
check "refuses an unknown default branch state" "$rc" "2"
has "explains the unknown default branch state" "$out" "cannot determine the default branch"
check "does not launch Codex when the default branch is unknown" "$(wc -c <"$LOG" | tr -d ' ')" "0"

R="$(new_repo run1work)"; P="$(new_plan "$R" auth)"

echo dirt >>"$R/src/a.py"
out=$("$S/codex_run.sh" "$P/T1.md" "$R" 2>&1); rc=$?
check "refuses a dirty product tree" "$rc" "2"
has "lists the offending file" "$out" "src/a.py"
git -C "$R" checkout -- .

echo "== dirty preflight failures stop before launch =="
REAL_GIT="$(command -v git)"
FAIL_GIT_BIN="$TMPROOT/run-failing-git"; mkdir -p "$FAIL_GIT_BIN"
cat >"$FAIL_GIT_BIN/git" <<EOF
#!/usr/bin/env bash
if [ "\${1:-}" = "-C" ] && [ "\${3:-}" = "diff" ] && [ "\${4:-}" = "--no-renames" ]; then
  exit 77
fi
exec "$REAL_GIT" "\$@"
EOF
chmod +x "$FAIL_GIT_BIN/git"
cp "$FAIL_GIT_BIN/git" "$FAIL_GIT_BIN/git.exe"
chmod +x "$FAIL_GIT_BIN/git.exe"
LOG="$TMPROOT/dirty-indeterminate-argv"; : >"$LOG"
out=$(PATH="$FAIL_GIT_BIN:$PATH" FAKE_CODEX_LOG="$LOG" \
  "$S/codex_run.sh" "$P/T1.md" "$R" 2>&1); rc=$?
check "indeterminate dirty state is refused" "$rc" "2"
has "dirty-state refusal is explained" "$out" "could not reliably determine"
check "indeterminate dirty state launches nothing" "$(grep -c '^ARGV:' "$LOG")" "0"

# The plan itself is untracked when /codex-spec has just written it. Holding it
# to the dirty check would mean the first task could never start.
out=$(FAKE_CODEX_TOUCH="src/a.py" "$S/codex_run.sh" "$P/T1.md" "$R" 2>&1); rc=$?
check "untracked plan does not block the first run" "$rc" "0"
has "scope reported" "$out" "scope: OK"

echo "== artifacts =="
RD="$(rundir_of "$R")"
for f in attempt-1/report.md attempt-1/events.jsonl attempt-1/stderr.log \
         attempt-1/meta.json attempt-1/scope.txt base_commit allowlist \
         contract.sha256 workdir thread_id .gitignore; do
  [ -f "$RD/$f" ] && ok "artifact $f" || bad "missing $f"
done
check "thread id captured" "$(cat "$RD/thread_id")" "thr-abc123"
hasnt "run dir hidden from git" "$(git -C "$R" status --porcelain)" "codex-runs"

echo "== metadata is encoded as JSON =="
R="$(new_repo run-json)"; P="$(new_plan "$R" auth)"
SPECIAL_MODEL=$'model"quote\\slash\nnext'
out=$(CODEX_MODEL="$SPECIAL_MODEL" FAKE_CODEX_TOUCH="src/a.py" \
  "$S/codex_run.sh" "$P/T1.md" "$R" 2>&1); rc=$?
check "run with JSON-special metadata succeeds" "$rc" "0"
RD="$(rundir_of "$R")"
json_model="$(python -c 'import json,sys; sys.stdout.buffer.write(json.load(open(sys.argv[1], encoding="utf-8"))["model"].encode("utf-8"))' \
  "$RD/attempt-1/meta.json" 2>/dev/null)"; json_rc=$?
check "run metadata is valid JSON" "$json_rc" "0"
check "run metadata preserves quotes, slashes, and newlines" "$json_model" "$SPECIAL_MODEL"

R="$(new_repo run-json-missing)"; P="$(new_plan "$R" auth)"
LOG="$TMPROOT/json-missing-argv"; : >"$LOG"
out=$(CODEX_JSON_CMD=definitely-missing-json-encoder FAKE_CODEX_LOG="$LOG" \
  "$S/codex_run.sh" "$P/T1.md" "$R" 2>&1); rc=$?
check "missing JSON encoder fails closed" "$rc" "2"
has "missing JSON encoder is explained" "$out" "JSON encoder"
check "missing JSON encoder launches nothing" "$(grep -c '^ARGV:' "$LOG")" "0"

echo "== interfaces are injected into the prompt =="
R="$(new_repo run2)"; P="$(new_plan "$R" auth)"
LOG="$TMPROOT/argv1"; : >"$LOG"
FAKE_CODEX_LOG="$LOG" FAKE_CODEX_TOUCH="src/a.py" "$S/codex_run.sh" "$P/T1.md" "$R" >/dev/null 2>&1
hasnt "nothing injected when interfaces.md is absent" "$(cat "$LOG")" "Verified interfaces"

printf 'get_token(user_id: str) -> Token\n' >"$P/interfaces.md"
git -C "$R" checkout -- . 2>/dev/null; git -C "$R" clean -qfd src 2>/dev/null
LOG="$TMPROOT/argv2"; : >"$LOG"
FAKE_CODEX_LOG="$LOG" FAKE_CODEX_TOUCH="src/a.py" "$S/codex_run.sh" "$P/T2.md" "$R" >/dev/null 2>&1
has "interfaces section injected" "$(cat "$LOG")" "Verified interfaces from completed tasks"
has "interface content injected" "$(cat "$LOG")" "get_token(user_id: str)"
has "task packet still present" "$(cat "$LOG")" "Do the next thing"

echo "== stdin is closed =="
# With a prompt argument present, Codex appends piped stdin to the prompt, so
# an inherited pipe would silently corrupt the task.
R="$(new_repo run3)"; P="$(new_plan "$R" auth)"
SL="$TMPROOT/stdin1"; : >"$SL"
printf 'LEAKED CONTENT\n' | FAKE_CODEX_STDIN_LOG="$SL" FAKE_CODEX_TOUCH="src/a.py" \
  "$S/codex_run.sh" "$P/T1.md" "$R" >/dev/null 2>&1
hasnt "caller stdin does not reach Codex" "$(cat "$SL")" "LEAKED CONTENT"

echo "== every hash backend produces a real digest =="
# `openssl dgst -sha256` prints `SHA2-256(stdin)= <hash>`, so taking the first
# field yields a constant — every file would hash alike and the integrity
# checks would wave anything through. Each backend is exercised separately,
# and against a known vector, because a backend that always agrees with itself
# still passes a same-tool comparison.
KNOWN=ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
printf abc >"$TMPROOT/abc"; printf xyz >"$TMPROOT/xyz"
for backend in "sha256sum" "shasum -a 256" "openssl dgst -sha256 -r"; do
  tool="${backend%% *}"
  if ! command -v "$tool" >/dev/null 2>&1; then
    printf '  SKIP  %s not installed\n' "$tool"; continue
  fi
  a="$(CODEX_HASH_CMD="$backend" bash -c '. "$0"; codex_hash_file "$1"' "$S/codex_lib.sh" "$TMPROOT/abc")"
  b="$(CODEX_HASH_CMD="$backend" bash -c '. "$0"; codex_hash_file "$1"' "$S/codex_lib.sh" "$TMPROOT/xyz")"
  check "$tool matches the known vector" "$a" "$KNOWN"
  [ "$a" != "$b" ] && ok "$tool distinguishes different files" \
                   || bad "$tool returns the same value for different files"
done

echo "== metadata tampering is fatal =="
R="$(new_repo run4)"; P="$(new_plan "$R" auth)"
out=$(FAKE_CODEX_TOUCH=".codex-instructions/auth/T1.allowlist" \
  "$S/codex_run.sh" "$P/T1.md" "$R" 2>&1); rc=$?
check "Codex widening its own allowlist fails the run" "$rc" "4"
has "explains the risk" "$out" "widen its own scope"

# Scoped to the plan being run: a second agent working another plan in the same
# repository must not be reported as Codex tampering with this one.
R="$(new_repo run4b)"; P="$(new_plan "$R" auth)"; new_plan "$R" billing >/dev/null
out=$(FAKE_CODEX_TOUCH="src/a.py .codex-instructions/billing/T1.md" \
  "$S/codex_run.sh" "$P/T1.md" "$R" 2>&1); rc=$?
check "another plan changing underfoot is not tampering" "$rc" "0"
hasnt "no false alarm" "$out" "modified the plan directory"

echo "== plan fingerprints bind file names =="
R="$(new_repo run4names)"; P="$(new_plan "$R" auth)"
BARRIER="$TMPROOT/plan-swap"; mkdir -p "$BARRIER"
CODEX_HASH_CMD="$TESTS_DIR/fixtures/hash-content-only" \
  FAKE_CODEX_BARRIER="$BARRIER" FAKE_CODEX_TOUCH="src/a.py" \
  "$S/codex_run.sh" "$P/T1.md" "$R" >"$TMPROOT/plan-swap.out" 2>&1 & pid=$!
for i in $(seq 1 200); do
  ls "$BARRIER"/ready-* >/dev/null 2>&1 && break
  sleep 0.05
done
mv "$P/T1.md" "$P/task.swap"
mv "$P/T2.md" "$P/T1.md"
mv "$P/task.swap" "$P/T2.md"
: >"$BARRIER/release"
wait "$pid"; rc=$?
check "swapping plan file contents is detected" "$rc" "4"
has "plan swap reports contract tampering" "$(cat "$TMPROOT/plan-swap.out")" "modified the plan directory"

echo "== frozen contract tampering is fatal =="
R="$(new_repo run4contract)"; P="$(new_plan "$R" auth)"
RD="$R/.codex-runs/frozen-run"; BARRIER="$TMPROOT/frozen-run"; mkdir -p "$BARRIER"
FAKE_CODEX_BARRIER="$BARRIER" FAKE_CODEX_TOUCH="docs/d.md" \
  "$S/codex_run.sh" "$P/T1.md" "$R" "$RD" >"$TMPROOT/frozen-run.out" 2>&1 & pid=$!
for i in $(seq 1 200); do
  ls "$BARRIER"/ready-* >/dev/null 2>&1 && break
  sleep 0.05
done
printf '*\n' >"$RD/allowlist"
: >"$BARRIER/release"
wait "$pid"; rc=$?
check "widening the frozen allowlist fails the run" "$rc" "4"
has "frozen allowlist tampering is explained" "$(cat "$TMPROOT/frozen-run.out")" "frozen contract"

echo "== run directories cannot collide =="
# The default name used to be a timestamp to the second, so two tasks started
# in the same second shared one directory and the second overwrote the first's
# frozen contract and attempt-1 while both were still in use.
R="$(new_repo run4c)"; P="$(new_plan "$R" auth)"
RD1="$(do_run "$R" "$P/T1.md")"
git -C "$R" add -A >/dev/null 2>&1; git -C "$R" commit -qm t1 >/dev/null 2>&1
RD2="$(do_run "$R" "$P/T2.md")"
[ -n "$RD1" ] && [ -n "$RD2" ] && ok "both runs reported a directory" || bad "missing RUNDIR output"
[ "$RD1" != "$RD2" ] && ok "same-second runs get distinct directories" \
                     || bad "collision: both used $RD1"
check "first run's contract survives" "$(cat "$RD1/task.md")" "$(cat "$P/T1.md")"
check "second run's contract is its own" "$(cat "$RD2/task.md")" "$(cat "$P/T2.md")"

git -C "$R" add -A >/dev/null 2>&1; git -C "$R" commit -qm t2 >/dev/null 2>&1
out=$("$S/codex_run.sh" "$P/T1.md" "$R" "$RD1" 2>&1); rc=$?
check "reusing a populated run directory is refused" "$rc" "2"
has "explains why" "$out" "already exists and is not empty"
out=$(FAKE_CODEX_TOUCH="src/a.py" "$S/codex_run.sh" "$P/T1.md" "$R" "$R/.codex-runs/fresh" 2>&1); rc=$?
check "an unused explicit path is accepted" "$rc" "0"

echo "== explicit run directories are reserved atomically =="
R="$(new_repo run4explicit)"; P="$(new_plan "$R" auth)"
RD="$R/.codex-runs/shared-explicit"
REAL_MKDIR="$(command -v mkdir)"
MKDIR_BIN="$TMPROOT/atomic-mkdir-bin"; mkdir -p "$MKDIR_BIN"
MKDIR_BARRIER="$TMPROOT/atomic-mkdir-barrier"; mkdir -p "$MKDIR_BARRIER"
cat >"$MKDIR_BIN/mkdir" <<EOF
#!/usr/bin/env bash
target="\${!#}"
case "\$target" in
  "$RD"|"$RD/attempt-1")
    : >"$MKDIR_BARRIER/ready-\$\$"
    while [ ! -e "$MKDIR_BARRIER/release" ]; do sleep 0.01; done
    ;;
esac
exec "$REAL_MKDIR" "\$@"
EOF
chmod +x "$MKDIR_BIN/mkdir"
LOG="$TMPROOT/explicit-concurrent-argv"; : >"$LOG"
PATH="$MKDIR_BIN:$PATH" FAKE_CODEX_LOG="$LOG" FAKE_CODEX_TOUCH="src/a.py" \
  "$S/codex_run.sh" "$P/T1.md" "$R" "$RD" >"$TMPROOT/explicit-1.out" 2>&1 & p1=$!
PATH="$MKDIR_BIN:$PATH" FAKE_CODEX_LOG="$LOG" FAKE_CODEX_TOUCH="src/a.py" \
  "$S/codex_run.sh" "$P/T1.md" "$R" "$RD" >"$TMPROOT/explicit-2.out" 2>&1 & p2=$!
for i in $(seq 1 200); do
  ready=$(ls "$MKDIR_BARRIER"/ready-* 2>/dev/null | wc -l | tr -d '[:space:]')
  [ "$ready" -ge 2 ] && break
  sleep 0.01
done
: >"$MKDIR_BARRIER/release"
wait "$p1"; rc1=$?
wait "$p2"; rc2=$?
if { [ "$rc1" -eq 0 ] && [ "$rc2" -eq 2 ]; } ||
   { [ "$rc1" -eq 2 ] && [ "$rc2" -eq 0 ]; }; then
  ok "exactly one explicit-directory contender succeeds"
else
  bad "explicit-directory contenders returned $rc1 and $rc2"
fi
check "only one Codex process uses attempt-1" "$(grep -c '^ARGV:' "$LOG")" "1"

echo "== scope gate uses the frozen allowlist =="
R="$(new_repo run5)"; P="$(new_plan "$R" auth)"
FAKE_CODEX_TOUCH="src/a.py" "$S/codex_run.sh" "$P/T1.md" "$R" >/dev/null 2>&1
RD="$(rundir_of "$R")"
printf 'src/*\n' >"$P/T1.allowlist.check"
check "frozen copy matches the plan at run time" \
  "$(cat "$RD/allowlist")" "$(cat "$P/T1.allowlist")"

echo "== non-git workdir =="
PLAIN="$TMPROOT/plain"; mkdir -p "$PLAIN"
out=$("$S/codex_run.sh" "$P/T1.md" "$PLAIN" 2>&1); rc=$?
check "refuses a scoped task without git" "$rc" "2"
has "explains the gate needs git" "$out" "scope gate needs git"
NOAL="$TMPROOT/noal.md"; printf 'do a thing\n' >"$NOAL"
out=$(FAKE_CODEX_TOUCH="q.txt" "$S/codex_run.sh" "$NOAL" "$PLAIN" 2>&1); rc=$?
check "unscoped task runs without git" "$rc" "0"
has "warns" "$out" "not a git repository"

echo "== resume: attempt isolation =="
R="$(new_repo res1)"; P="$(new_plan "$R" auth)"
FAKE_CODEX_TOUCH="src/a.py" "$S/codex_run.sh" "$P/T1.md" "$R" >/dev/null 2>&1
RD="$(rundir_of "$R")"
r1="$(cat "$RD/attempt-1/report.md")"; e1="$(cat "$RD/attempt-1/events.jsonl")"
printf 'root cause: foo\n' >"$P/T1.hint-1.md"
out=$(FAKE_CODEX_TOUCH="src/a.py" "$S/codex_resume.sh" "$P/T1.hint-1.md" "$R" "$RD" 2>&1); rc=$?
check "resume succeeds" "$rc" "0"
[ -d "$RD/attempt-2" ] && ok "attempt-2 created" || bad "no attempt-2"
check "attempt-1 report intact" "$(cat "$RD/attempt-1/report.md")" "$r1"
check "attempt-1 events intact" "$(cat "$RD/attempt-1/events.jsonl")" "$e1"

echo "== resume metadata is encoded as JSON =="
R="$(new_repo resume-json)"; P="$(new_plan "$R" auth)"
FAKE_CODEX_TOUCH="src/a.py" "$S/codex_run.sh" "$P/T1.md" "$R" >/dev/null 2>&1
RD="$(rundir_of "$R")"; printf 'hint\n' >"$P/T1.hint-1.md"
SPECIAL_MODEL=$'resume"quote\\slash\nnext'
out=$(CODEX_MODEL="$SPECIAL_MODEL" FAKE_CODEX_TOUCH="src/a.py" \
  "$S/codex_resume.sh" "$P/T1.hint-1.md" "$R" "$RD" 2>&1); rc=$?
check "resume with JSON-special metadata succeeds" "$rc" "0"
json_model="$(python -c 'import json,sys; sys.stdout.buffer.write(json.load(open(sys.argv[1], encoding="utf-8"))["model"].encode("utf-8"))' \
  "$RD/attempt-2/meta.json" 2>/dev/null)"; json_rc=$?
check "resume metadata is valid JSON" "$json_rc" "0"
check "resume metadata preserves quotes, slashes, and newlines" "$json_model" "$SPECIAL_MODEL"

echo "== resume: targeted session, correct flag order =="
LOG="$TMPROOT/argv3"; : >"$LOG"
FAKE_CODEX_LOG="$LOG" FAKE_CODEX_TOUCH="src/a.py" \
  "$S/codex_resume.sh" "$P/T1.hint-1.md" "$R" "$RD" >/dev/null 2>&1
argv="$(grep '^ARGV:' "$LOG" | tail -1)"
has "resumes the recorded session, not --last" "$argv" "resume thr-abc123"
hasnt "does not fall back to --last" "$argv" "--last"
# `--cd` and `--sandbox` belong to `exec`; after the `resume` subcommand the
# CLI rejects them.
case "$argv" in
  *"exec --cd"*) ok "exec options precede the subcommand" ;;
  *) bad "options misplaced: $argv" ;;
esac
case "$argv" in
  *"--json resume"*) ok "resume comes after the options" ;;
  *) bad "subcommand misplaced: $argv" ;;
esac

echo "== resume: extra args are not dropped =="
# A fresh run directory: the attempt cap counts attempts per run, and the
# resumes above have already used this one up.
R="$(new_repo res1b)"; P="$(new_plan "$R" auth)"
FAKE_CODEX_TOUCH="src/a.py" "$S/codex_run.sh" "$P/T1.md" "$R" >/dev/null 2>&1
RD="$(rundir_of "$R")"; printf 'hint\n' >"$P/T1.hint-1.md"
LOG="$TMPROOT/argv4"; : >"$LOG"
FAKE_CODEX_LOG="$LOG" CODEX_EXTRA_ARGS="--config foo=bar" FAKE_CODEX_TOUCH="src/a.py" \
  "$S/codex_resume.sh" "$P/T1.hint-1.md" "$R" "$RD" >/dev/null 2>&1
has "CODEX_EXTRA_ARGS reaches resume" "$(grep '^ARGV:' "$LOG" | tail -1)" "--config foo=bar"

echo "== resume: mode selection =="
R="$(new_repo res2)"; P="$(new_plan "$R" auth)"
FAKE_CODEX_TOUCH="src/a.py" "$S/codex_run.sh" "$P/T1.md" "$R" >/dev/null 2>&1
RD="$(rundir_of "$R")"
printf 'hint\n' >"$P/T1.hint-1.md"
LOG="$TMPROOT/argv5"; : >"$LOG"
FAKE_CODEX_NO_RESUME=1 FAKE_CODEX_LOG="$LOG" FAKE_CODEX_TOUCH="src/a.py" \
  "$S/codex_resume.sh" "$P/T1.hint-1.md" "$R" "$RD" >/dev/null 2>&1
hasnt "old CLI falls back to fresh" "$(grep '^ARGV:' "$LOG" | tail -1)" " resume"
check "exactly one run charged" "$(grep -c '^ARGV:' "$LOG")" "1"

: >"$RD/thread_id"
LOG="$TMPROOT/argv6"; : >"$LOG"
FAKE_CODEX_LOG="$LOG" FAKE_CODEX_TOUCH="src/a.py" \
  "$S/codex_resume.sh" "$P/T1.hint-1.md" "$R" "$RD" >/dev/null 2>&1
hasnt "no session id means fresh, never --last" "$(grep '^ARGV:' "$LOG" | tail -1)" "--last"
out=$(CODEX_RESUME_MODE=resume "$S/codex_resume.sh" "$P/T1.hint-1.md" "$R" "$RD" 2>&1); rc=$?
check "explicit resume without an id is an error" "$rc" "2"
out=$(CODEX_RESUME_MODE=bogus "$S/codex_resume.sh" "$P/T1.hint-1.md" "$R" "$RD" 2>&1); rc=$?
check "unknown mode rejected" "$rc" "2"

echo "== resume: a task failure is not mistaken for an unsupported CLI =="
R="$(new_repo res3)"; P="$(new_plan "$R" auth)"
FAKE_CODEX_TOUCH="src/a.py" "$S/codex_run.sh" "$P/T1.md" "$R" >/dev/null 2>&1
RD="$(rundir_of "$R")"; printf 'hint\n' >"$P/T1.hint-1.md"
LOG="$TMPROOT/argv7"; : >"$LOG"
FAKE_CODEX_RC=1 FAKE_CODEX_LOG="$LOG" \
  "$S/codex_resume.sh" "$P/T1.hint-1.md" "$R" "$RD" >/dev/null 2>&1; rc=$?
check "propagates Codex's exit code" "$rc" "1"
check "no redundant second run" "$(grep -c '^ARGV:' "$LOG")" "1"

echo "== resume: the attempt cap is enforced, not just documented =="
R="$(new_repo res4)"; P="$(new_plan "$R" auth)"
FAKE_CODEX_TOUCH="src/a.py" "$S/codex_run.sh" "$P/T1.md" "$R" >/dev/null 2>&1
RD="$(rundir_of "$R")"; printf 'hint\n' >"$P/T1.hint-1.md"
FAKE_CODEX_TOUCH="src/a.py" "$S/codex_resume.sh" "$P/T1.hint-1.md" "$R" "$RD" >/dev/null 2>&1
FAKE_CODEX_TOUCH="src/a.py" "$S/codex_resume.sh" "$P/T1.hint-1.md" "$R" "$RD" >/dev/null 2>&1
out=$(FAKE_CODEX_TOUCH="src/a.py" "$S/codex_resume.sh" "$P/T1.hint-1.md" "$R" "$RD" 2>&1); rc=$?
check "fourth attempt refused" "$rc" "2"
has "tells the orchestrator to escalate" "$out" "escalate"
out=$(CODEX_MAX_ATTEMPTS=0 FAKE_CODEX_TOUCH="src/a.py" \
  "$S/codex_resume.sh" "$P/T1.hint-1.md" "$R" "$RD" 2>&1); rc=$?
check "cap can be lifted deliberately" "$rc" "0"

echo "== resume: the attempt cap is validated =="
R="$(new_repo res4invalid)"; P="$(new_plan "$R" auth)"
FAKE_CODEX_TOUCH="src/a.py" "$S/codex_run.sh" "$P/T1.md" "$R" >/dev/null 2>&1
RD="$(rundir_of "$R")"; printf 'hint\n' >"$P/T1.hint-1.md"
for invalid in bogus -1 1.5; do
  LOG="$TMPROOT/invalid-${invalid//[^[:alnum:]]/_}"; : >"$LOG"
  out=$(CODEX_MAX_ATTEMPTS="$invalid" FAKE_CODEX_LOG="$LOG" \
    "$S/codex_resume.sh" "$P/T1.hint-1.md" "$R" "$RD" 2>&1); rc=$?
  check "rejects CODEX_MAX_ATTEMPTS=$invalid" "$rc" "2"
  has "explains invalid cap $invalid" "$out" "nonnegative integer"
  check "invalid cap $invalid launches nothing" "$(grep -c '^ARGV:' "$LOG")" "0"
done

echo "== resume: a rejected call must not burn an attempt =="
# Attempts are counted by directory, so creating one before the mode checks
# pass would leave an empty attempt behind and consume a slot off the cap
# without Codex ever running.
R="$(new_repo res6)"; P="$(new_plan "$R" auth)"
FAKE_CODEX_TOUCH="src/a.py" "$S/codex_run.sh" "$P/T1.md" "$R" >/dev/null 2>&1
RD="$(rundir_of "$R")"; printf 'hint\n' >"$P/T1.hint-1.md"
: >"$RD/thread_id"
CODEX_RESUME_MODE=resume "$S/codex_resume.sh" "$P/T1.hint-1.md" "$R" "$RD" >/dev/null 2>&1
[ -d "$RD/attempt-2" ] && bad "empty attempt-2 left behind" || ok "no attempt left behind"
CODEX_RESUME_MODE=bogus "$S/codex_resume.sh" "$P/T1.hint-1.md" "$R" "$RD" >/dev/null 2>&1
[ -d "$RD/attempt-2" ] && bad "empty attempt-2 left behind" || ok "bad mode leaves nothing"
FAKE_CODEX_TOUCH="src/a.py" "$S/codex_resume.sh" "$P/T1.hint-1.md" "$R" "$RD" >/dev/null 2>&1
[ -d "$RD/attempt-2" ] && ok "a real resume still opens attempt-2" || bad "attempt-2 missing"

echo "== resume: reservation failures are finite and classified =="
R="$(new_repo res6file)"; P="$(new_plan "$R" auth)"
FAKE_CODEX_TOUCH="src/a.py" "$S/codex_run.sh" "$P/T1.md" "$R" >/dev/null 2>&1
RD="$(rundir_of "$R")"; printf 'hint\n' >"$P/T1.hint-1.md"
: >"$RD/attempt-2"
LOG="$TMPROOT/file-collision-argv"; : >"$LOG"
CAPTURE="$TMPROOT/file-collision.out"
run_with_deadline "$CAPTURE" env FAKE_CODEX_LOG="$LOG" \
  "$S/codex_resume.sh" "$P/T1.hint-1.md" "$R" "$RD"; rc=$?
out="$(cat "$CAPTURE")"
check "an attempt path occupied by a file fails closed" "$rc" "2"
has "file collision is explained" "$out" "could not reserve"
check "file collision launches nothing" "$(grep -c '^ARGV:' "$LOG")" "0"

R="$(new_repo res6bounded)"; P="$(new_plan "$R" auth)"
FAKE_CODEX_TOUCH="src/a.py" "$S/codex_run.sh" "$P/T1.md" "$R" >/dev/null 2>&1
RD="$(rundir_of "$R")"; printf 'hint\n' >"$P/T1.hint-1.md"
REAL_MKDIR="$(command -v mkdir)"
COLLISION_BIN="$TMPROOT/collision-mkdir-bin"; mkdir -p "$COLLISION_BIN"
COLLISION_LOG="$TMPROOT/collision-mkdir-log"; : >"$COLLISION_LOG"
cat >"$COLLISION_BIN/mkdir" <<EOF
#!/usr/bin/env bash
target="\${!#}"
case "\$target" in
  "$RD"/attempt-*)
    "$REAL_MKDIR" "\$target" 2>/dev/null || true
    printf '%s\n' "\$target" >>"$COLLISION_LOG"
    sleep 0.02
    exit 1
    ;;
esac
exec "$REAL_MKDIR" "\$@"
EOF
chmod +x "$COLLISION_BIN/mkdir"
LOG="$TMPROOT/bounded-collision-argv"; : >"$LOG"
CAPTURE="$TMPROOT/bounded-collision.out"
run_with_deadline "$CAPTURE" env PATH="$COLLISION_BIN:$PATH" CODEX_MAX_ATTEMPTS=0 FAKE_CODEX_LOG="$LOG" \
  "$S/codex_resume.sh" "$P/T1.hint-1.md" "$R" "$RD"; rc=$?
out="$(cat "$CAPTURE")"
check "verified directory collisions stop at an internal bound" "$rc" "2"
has "collision bound is explained" "$out" "could not reserve"
collision_count="$(wc -l <"$COLLISION_LOG" | tr -d '[:space:]')"
[ "$collision_count" -le 32 ] \
  && ok "reservation retry bound is small ($collision_count)" \
  || bad "reservation retried $collision_count times"
check "bounded collisions launch nothing" "$(grep -c '^ARGV:' "$LOG")" "0"

echo "== resume: concurrent attempts reserve unique evidence =="
R="$(new_repo res6concurrent)"; P="$(new_plan "$R" auth)"
FAKE_CODEX_TOUCH="src/a.py" "$S/codex_run.sh" "$P/T1.md" "$R" >/dev/null 2>&1
RD="$(rundir_of "$R")"; printf 'hint\n' >"$P/T1.hint-1.md"
BARRIER="$TMPROOT/resume-concurrent"; mkdir -p "$BARRIER"
FAKE_CODEX_BARRIER="$BARRIER" FAKE_CODEX_TOUCH="src/a.py" \
  "$S/codex_resume.sh" "$P/T1.hint-1.md" "$R" "$RD" >"$TMPROOT/concurrent-1.out" 2>&1 & p1=$!
FAKE_CODEX_BARRIER="$BARRIER" FAKE_CODEX_TOUCH="src/a.py" \
  "$S/codex_resume.sh" "$P/T1.hint-1.md" "$R" "$RD" >"$TMPROOT/concurrent-2.out" 2>&1 & p2=$!
for i in $(seq 1 200); do
  ready=$(ls "$BARRIER"/ready-* 2>/dev/null | wc -l | tr -d '[:space:]')
  [ "$ready" -ge 2 ] && break
  sleep 0.05
done
: >"$BARRIER/release"
wait "$p1"; rc1=$?
wait "$p2"; rc2=$?
check "first concurrent resume succeeds" "$rc1" "0"
check "second concurrent resume succeeds" "$rc2" "0"
[ -d "$RD/attempt-2" ] && [ -d "$RD/attempt-3" ] \
  && ok "concurrent resumes get distinct attempt directories" \
  || bad "concurrent resumes did not reserve attempt-2 and attempt-3"

echo "== the contract is frozen at run time =="
R="$(new_repo res7)"; P="$(new_plan "$R" auth)"
printf 'pytest -q\n' >"$P/T1.test"
FAKE_CODEX_TOUCH="src/a.py" "$S/codex_run.sh" "$P/T1.md" "$R" >/dev/null 2>&1
RD="$(rundir_of "$R")"
for f in task.md allowlist test; do
  [ -f "$RD/$f" ] && ok "frozen $f" || bad "missing frozen $f"
done
check "per-task test file wins" "$(cat "$RD/test")" "pytest -q"
check "frozen packet matches" "$(cat "$RD/task.md")" "$(cat "$P/T1.md")"

echo "== resume: frozen run identity and scope prerequisites =="
R="$(new_repo res7identity)"; P="$(new_plan "$R" auth)"
FAKE_CODEX_TOUCH="src/a.py" "$S/codex_run.sh" "$P/T1.md" "$R" >/dev/null 2>&1
RD="$(rundir_of "$R")"; printf 'hint\n' >"$P/T1.hint-1.md"
OTHER="$(new_repo res7other)"
LOG="$TMPROOT/wrong-workdir"; : >"$LOG"
out=$(FAKE_CODEX_LOG="$LOG" "$S/codex_resume.sh" "$P/T1.hint-1.md" "$OTHER" "$RD" 2>&1); rc=$?
check "resume rejects a different workdir" "$rc" "2"
has "different workdir is explained" "$out" "does not match"
check "different workdir launches nothing" "$(grep -c '^ARGV:' "$LOG")" "0"

R="$(new_repo res7nogit)"; P="$(new_plan "$R" auth)"
FAKE_CODEX_TOUCH="src/a.py" "$S/codex_run.sh" "$P/T1.md" "$R" >/dev/null 2>&1
RD="$(rundir_of "$R")"; printf 'hint\n' >"$P/T1.hint-1.md"
mv "$R/.git" "$R/git.saved"
LOG="$TMPROOT/no-git"; : >"$LOG"
out=$(FAKE_CODEX_LOG="$LOG" "$S/codex_resume.sh" "$P/T1.hint-1.md" "$R" "$RD" 2>&1); rc=$?
check "resume refuses a workdir that is no longer Git" "$rc" "2"
has "missing Git workdir is explained" "$out" "not a git repository"
check "missing Git workdir launches nothing" "$(grep -c '^ARGV:' "$LOG")" "0"

R="$(new_repo res7base)"; P="$(new_plan "$R" auth)"
FAKE_CODEX_TOUCH="src/a.py" "$S/codex_run.sh" "$P/T1.md" "$R" >/dev/null 2>&1
RD="$(rundir_of "$R")"; printf 'hint\n' >"$P/T1.hint-1.md"; : >"$RD/base_commit"
LOG="$TMPROOT/no-base"; : >"$LOG"
out=$(FAKE_CODEX_LOG="$LOG" "$S/codex_resume.sh" "$P/T1.hint-1.md" "$R" "$RD" 2>&1); rc=$?
check "resume refuses a missing frozen base" "$rc" "2"
has "missing frozen base is explained" "$out" "base commit"
check "missing frozen base launches nothing" "$(grep -c '^ARGV:' "$LOG")" "0"

echo "== resume: frozen task tampering is fatal before launch =="
R="$(new_repo res7contract)"; P="$(new_plan "$R" auth)"
FAKE_CODEX_TOUCH="src/a.py" "$S/codex_run.sh" "$P/T1.md" "$R" >/dev/null 2>&1
RD="$(rundir_of "$R")"; printf 'hint\n' >"$P/T1.hint-1.md"; printf 'rewritten\n' >"$RD/task.md"
LOG="$TMPROOT/tampered-task"; : >"$LOG"
out=$(FAKE_CODEX_LOG="$LOG" "$S/codex_resume.sh" "$P/T1.hint-1.md" "$R" "$RD" 2>&1); rc=$?
check "resume rejects a rewritten frozen task" "$rc" "4"
has "rewritten frozen task is explained" "$out" "frozen contract"
check "rewritten frozen task launches nothing" "$(grep -c '^ARGV:' "$LOG")" "0"

echo "== resume: scope baseline stays the task's start =="
R="$(new_repo res5)"; P="$(new_plan "$R" auth)"
FAKE_CODEX_TOUCH="src/a.py" "$S/codex_run.sh" "$P/T1.md" "$R" >/dev/null 2>&1
RD="$(rundir_of "$R")"; printf 'hint\n' >"$P/T1.hint-1.md"
out=$(FAKE_CODEX_TOUCH="docs/d.md" "$S/codex_resume.sh" "$P/T1.hint-1.md" "$R" "$RD" 2>&1); rc=$?
check "cumulative violation caught" "$rc" "3"

finish
