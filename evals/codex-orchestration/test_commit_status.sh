#!/usr/bin/env bash
# codex_commit.sh / codex_status.sh: commit and status are evidence gates.
set -uo pipefail
. "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

run_task() { do_run "$1" "$2/$3.md" "${4:-src/a.py}"; }

echo "== commit gate refuses unsafe evidence =="
R="$(new_repo commit-empty)"; P="$(new_plan "$R" auth)"; RD="$(run_task "$R" "$P" T1)"
git -C "$R" checkout -- src 2>/dev/null
out="$("$S/codex_commit.sh" "$P" T1 "$R" "$RD" 2>&1)"; rc=$?
check "no product change is refused" "$rc" "1"
has "no-product diagnostic" "$out" "changed no product files"

R="$(new_repo commit-scope)"; P="$(new_plan "$R" auth)"; RD="$(run_task "$R" "$P" T1 docs/d.md)"; before="$(ncommits "$R")"
out="$("$S/codex_commit.sh" "$P" T1 "$R" "$RD" 2>&1)"; rc=$?
check "out-of-scope changes are refused" "$rc" "3"
check "scope violation makes no commit" "$(ncommits "$R")" "$before"

R="$(new_repo commit-tests)"; P="$(new_plan "$R" auth)"; printf 'false\n' >"$P/test"; RD="$(run_task "$R" "$P" T1)"; before="$(ncommits "$R")"
out="$("$S/codex_commit.sh" "$P" T1 "$R" "$RD" 2>&1)"; rc=$?
check "failing frozen test blocks commit" "$rc" "1"
has "test diagnostic" "$out" "test gate failed"
check "red test makes no commit" "$(ncommits "$R")" "$before"

R="$(new_repo commit-head)"; P="$(new_plan "$R" auth)"; RD="$(run_task "$R" "$P" T1)"
git -C "$R" add -A && git -C "$R" commit -qm intruder
out="$("$S/codex_commit.sh" "$P" T1 "$R" "$RD" 2>&1)"; rc=$?
check "moved HEAD is refused" "$rc" "5"
has "HEAD diagnostic" "$out" "HEAD moved"

R="$(new_repo commit-contract)"; P="$(new_plan "$R" auth)"; RD="$(run_task "$R" "$P" T1)"; before="$(ncommits "$R")"
printf 'src/*\ndocs/*\n' >"$P/T1.allowlist"
out="$("$S/codex_commit.sh" "$P" T1 "$R" "$RD" 2>&1)"; rc=$?
check "live widened allowlist is refused" "$rc" "6"
has "allowlist drift named" "$out" "T1.allowlist"
check "drift makes no commit" "$(ncommits "$R")" "$before"

R="$(new_repo commit-plan-id)"; P="$(new_plan "$R" auth)"; RD="$(run_task "$R" "$P" T1)"; before="$(ncommits "$R")"
printf 'replacement-plan-id\n' >"$P/plan-id"
out="$("$S/codex_commit.sh" "$P" T1 "$R" "$RD" 2>&1)"; rc=$?
check "live plan identity drift is refused" "$rc" "6"
has "plan identity drift is named" "$out" "plan-id"
check "plan identity drift makes no commit" "$(ncommits "$R")" "$before"

# A workspace-writable run directory is untrusted. The trusted Git anchor
# written by codex_run must be verified before frozen members are used.
R="$(new_repo commit-anchor)"; P="$(new_plan "$R" auth)"; RD="$(run_task "$R" "$P" T1)"; before="$(ncommits "$R")"
printf 'tampered\n' >>"$RD/task.md"
out="$("$S/codex_commit.sh" "$P" T1 "$R" "$RD" 2>&1)"; rc=$?
check "tampered run contract is refused" "$rc" "6"
has "contract diagnostic" "$out" "frozen contract"
check "tampered contract makes no commit" "$(ncommits "$R")" "$before"

R="$(new_repo commit-missing-base)"; P="$(new_plan "$R" auth)"; RD="$(run_task "$R" "$P" T1)"
rm -f "$RD/base_commit"
out="$("$S/codex_commit.sh" "$P" T1 "$R" "$RD" 2>&1)"; rc=$?
check "missing baseline is refused" "$rc" "6"
has "baseline diagnostic" "$out" "frozen contract"

R="$(new_repo commit-post-test)"; P="$(new_plan "$R" auth)"; printf 'echo coverage > coverage.xml\n' >"$P/test"; RD="$(run_task "$R" "$P" T1)"; before="$(ncommits "$R")"
out="$("$S/codex_commit.sh" "$P" T1 "$R" "$RD" 2>&1)"; rc=$?
check "post-test out-of-scope file is refused" "$rc" "3"
has "post-test diagnostic" "$out" "after tests"
check "post-test scope makes no commit" "$(ncommits "$R")" "$before"

echo "== commit verdict inputs live only in parent-shell memory =="
R="$(new_repo commit-allowlist-single-read)"; P="$(new_plan "$R" auth)"; RD="$(run_task "$R" "$P" T1 docs/d.md)"
HASH_RACE_DIR="$TMPROOT/hash-race"; mkdir -p "$HASH_RACE_DIR"
printf 'src/*\n' >"$HASH_RACE_DIR/original-allowlist"
printf '0\n' >"$HASH_RACE_DIR/count"
REAL_SHA256SUM="$(command -v sha256sum)"
cat >"$HASH_RACE_DIR/hash-and-replace" <<EOF
#!/usr/bin/env bash
input="$HASH_RACE_DIR/input.\$\$"
cat >"\$input"
"$REAL_SHA256SUM" "\$input"
if cmp -s "\$input" "$HASH_RACE_DIR/original-allowlist"; then
  count="\$(cat "$HASH_RACE_DIR/count")"
  count=\$((count + 1))
  printf '%s\n' "\$count" >"$HASH_RACE_DIR/count"
  if [ "\$count" -eq 2 ]; then
    printf '*\n' >"$RD/allowlist"
  fi
fi
rm -f "\$input"
EOF
chmod +x "$HASH_RACE_DIR/hash-and-replace"
before="$(ncommits "$R")"
out="$(CODEX_HASH_CMD="$HASH_RACE_DIR/hash-and-replace" \
  "$S/codex_commit.sh" "$P" T1 "$R" "$RD" 2>&1)"; rc=$?
check "allowlist hash/parse race retains the originally verified scope" "$rc" "3"
has "single-read allowlist race reports the original scope violation" "$out" "before tests"
check "allowlist read race makes no commit" "$(ncommits "$R")" "$before"

R="$(new_repo commit-snapshot-probe)"; P="$(new_plan "$R" auth)"
cat >"$P/test" <<'EOF'
run_dir="$(ls -dt .codex-runs/* | head -1)"; snapshot="$(find .git/codex-orchestration-contracts -maxdepth 1 -type f -name 'allowlist.*' 2>/dev/null | head -1)"; if [ -n "$snapshot" ]; then printf '*\n' >"$snapshot"; printf 'found\n' >"$run_dir/snapshot-probe"; else printf 'none\n' >"$run_dir/snapshot-probe"; fi
EOF
RD="$(run_task "$R" "$P" T1)"
out="$("$S/codex_commit.sh" "$P" T1 "$R" "$RD" 2>&1)"; rc=$?
check "snapshot overwrite probe cannot disrupt a valid task" "$rc" "0"
check "no mutable allowlist snapshot exists under Git metadata" "$(cat "$RD/snapshot-probe")" "none"

echo "== live plan drift is independently fatal =="
R="$(new_repo commit-live-plan-only)"; P="$(new_plan "$R" auth)"
cat >"$P/test" <<'EOF'
printf '*\n' >.codex-instructions/auth/T1.allowlist
EOF
RD="$(run_task "$R" "$P" T1)"; before="$(ncommits "$R")"
out="$("$S/codex_commit.sh" "$P" T1 "$R" "$RD" 2>&1)"; rc=$?
check "live allowlist-only drift is refused" "$rc" "6"
has "live allowlist drift is named" "$out" "T1.allowlist"
check "live plan drift makes no commit" "$(ncommits "$R")" "$before"

echo "== Git-metadata overwrite cannot widen live scope =="
R="$(new_repo commit-snapshot-bypass)"; P="$(new_plan "$R" auth)"
cat >"$P/test" <<'EOF'
snapshot="$(find .git/codex-orchestration-contracts -maxdepth 1 -type f -name 'allowlist.*' 2>/dev/null | head -1)"; [ -z "$snapshot" ] || printf '*\n' >"$snapshot"; printf '*\n' >.codex-instructions/auth/T1.allowlist; printf 'escaped\n' >docs/escaped.txt
EOF
RD="$(run_task "$R" "$P" T1)"; before="$(ncommits "$R")"
out="$("$S/codex_commit.sh" "$P" T1 "$R" "$RD" 2>&1)"; rc=$?
check "snapshot and live-plan rewrite cannot bypass the gate" "$rc" "6"
check "snapshot bypass makes no commit" "$(ncommits "$R")" "$before"

echo "== passing tests cannot change the frozen candidate =="
R="$(new_repo commit-test-adds-path)"; P="$(new_plan "$R" auth)"
cat >"$P/test" <<'EOF'
printf 'injected\n' >src/test-added.py
EOF
RD="$(run_task "$R" "$P" T1)"; before="$(ncommits "$R")"
out="$("$S/codex_commit.sh" "$P" T1 "$R" "$RD" 2>&1)"; rc=$?
check "a passing test cannot add a candidate path" "$rc" "2"
has "test-added path drift is explained" "$out" "product path set changed"
check "test-added path makes no commit" "$(ncommits "$R")" "$before"

R="$(new_repo commit-product-list-tamper)"; P="$(new_plan "$R" auth)"
PRODUCT_TAMPER_HOOK="$TMPROOT/rewrite-product-list"
cat >"$PRODUCT_TAMPER_HOOK" <<'EOF'
#!/usr/bin/env bash
set -eu
run_dir="$(ls -dt .codex-runs/* | head -1)"
target=""
for candidate in "$TMPDIR"/*; do
  [ -f "$candidate" ] || continue
  values=()
  mapfile -d '' -t values <"$candidate" 2>/dev/null || continue
  if [ "${#values[@]}" -eq 1 ] && [ "${values[0]}" = "src/a.py" ]; then
    target="$candidate"
    break
  fi
done
printf 'injected\n' >src/test-added.py
if [ -n "$target" ]; then
  printf 'src/a.py\0src/test-added.py\0' >"$target"
  printf 'found\n' >"$run_dir/product-list-probe"
else
  printf 'none\n' >"$run_dir/product-list-probe"
fi
EOF
chmod +x "$PRODUCT_TAMPER_HOOK"
printf '"%s"\n' "$PRODUCT_TAMPER_HOOK" >"$P/test"
RD="$(run_task "$R" "$P" T1)"; before="$(ncommits "$R")"
PRODUCT_TMP="$TMPROOT/product-list-tamper"; mkdir -p "$PRODUCT_TMP"
out="$(TMPDIR="$PRODUCT_TMP" "$S/codex_commit.sh" "$P" T1 "$R" "$RD" 2>&1)"; rc=$?
check "TMPDIR rewriting cannot replace the retained product path set" "$rc" "2"
has "TMPDIR path-set tampering is explained" "$out" "product path set changed"
check "TMPDIR path-set tampering makes no commit" "$(ncommits "$R")" "$before"

R="$(new_repo commit-test-mutates-content)"; P="$(new_plan "$R" auth)"
cat >"$P/test" <<'EOF'
printf 'test mutation\n' >>src/a.py
EOF
RD="$(run_task "$R" "$P" T1)"; before="$(ncommits "$R")"
out="$("$S/codex_commit.sh" "$P" T1 "$R" "$RD" 2>&1)"; rc=$?
check "a passing test cannot replace frozen candidate content" "$rc" "2"
has "test-mutated content drift is explained" "$out" "candidate tree changed after tests"
check "test-mutated content makes no commit" "$(ncommits "$R")" "$before"

R="$(new_repo commit-restored-stat-content)"; P="$(new_plan "$R" auth)"
RESTORE_STAT_HOOK="$TMPROOT/restore-stat-content"
cat >"$RESTORE_STAT_HOOK" <<'EOF'
#!/usr/bin/env bash
set -eu
reference="$(mktemp)"
cp -p src/a.py "$reference"
perl -0777 -i -pe 'substr($_, 0, 1) = substr($_, 0, 1) eq "X" ? "Y" : "X"' src/a.py
touch -r "$reference" src/a.py
rm -f "$reference"
EOF
chmod +x "$RESTORE_STAT_HOOK"
printf '"%s"\n' "$RESTORE_STAT_HOOK" >"$P/test"
RD="$(run_task "$R" "$P" T1)"; before="$(ncommits "$R")"
git -C "$R" config core.trustctime false
git -C "$R" config core.checkStat minimal
out="$("$S/codex_commit.sh" "$P" T1 "$R" "$RD" 2>&1)"; rc=$?
check "same-size content with restored stat metadata is refused" "$rc" "2"
has "restored-stat content drift is explained" "$out" "candidate tree changed"
check "restored-stat mutation makes no commit" "$(ncommits "$R")" "$before"

R="$(new_repo commit-plan-symlink)"; P="$(new_plan "$R" auth)"
PLAN_SYMLINK_HOOK="$TMPROOT/add-plan-symlink"
cat >"$PLAN_SYMLINK_HOOK" <<'EOF'
#!/usr/bin/env bash
set -eu
run_dir="$(ls -dt .codex-runs/* | head -1)"
if ln -s T1.md .codex-instructions/auth/future-link 2>/dev/null &&
   [ -L .codex-instructions/auth/future-link ] &&
   [ "$(readlink .codex-instructions/auth/future-link)" = "T1.md" ]; then
  printf 'supported\n' >"$run_dir/symlink-probe"
else
  rm -f .codex-instructions/auth/future-link
  printf 'unsupported\n' >"$run_dir/symlink-probe"
fi
EOF
chmod +x "$PLAN_SYMLINK_HOOK"
printf '"%s"\n' "$PLAN_SYMLINK_HOOK" >"$P/test"
RD="$(run_task "$R" "$P" T1)"; before="$(ncommits "$R")"
out="$("$S/codex_commit.sh" "$P" T1 "$R" "$RD" 2>&1)"; rc=$?
if [ "$(cat "$RD/symlink-probe")" = "supported" ]; then
  check "future active-plan symlink drift is refused" "$rc" "6"
  has "future plan symlink drift is explained" "$out" "plan directory"
  check "future plan symlink makes no commit" "$(ncommits "$R")" "$before"
else
  ok "future plan symlink regression skipped: filesystem did not create an exact symbolic link"
fi

echo "== early private-index failures clean every reservation =="
R="$(new_repo commit-cleanup)"; P="$(new_plan "$R" auth)"; RD="$(run_task "$R" "$P" T1)"
CLEAN_TMP="$TMPROOT/commit-cleanup-tmp"; mkdir -p "$CLEAN_TMP"
REAL_GIT="$(command -v git)"
FAIL_READ_TREE_BIN="$TMPROOT/fail-read-tree-bin"; mkdir -p "$FAIL_READ_TREE_BIN"
cat >"$FAIL_READ_TREE_BIN/git" <<EOF
#!/usr/bin/env bash
for arg in "\$@"; do
  [ "\$arg" = "read-tree" ] && exit 77
done
exec "$REAL_GIT" "\$@"
EOF
chmod +x "$FAIL_READ_TREE_BIN/git"
cp "$FAIL_READ_TREE_BIN/git" "$FAIL_READ_TREE_BIN/git.exe"
chmod +x "$FAIL_READ_TREE_BIN/git.exe"
out="$(TMPDIR="$CLEAN_TMP" PATH="$FAIL_READ_TREE_BIN:$PATH" \
  "$S/codex_commit.sh" "$P" T1 "$R" "$RD" 2>&1)"; rc=$?
check "private-index initialization failure is fail-closed" "$rc" "2"
has "private-index failure is explained" "$out" "initialize the pre-test isolated Git index"
leftovers="$(find "$CLEAN_TMP" -mindepth 1 -maxdepth 1 -print | wc -l | tr -d '[:space:]')"
check "early failure leaves no temporary files or directories" "$leftovers" "0"
commit_lock="$(git -C "$R" rev-parse --git-path codex-orchestration-commit.lock)"
[ -e "$commit_lock" ] && bad "early failure left the commit lock" || ok "early failure releases the commit lock"

R="$(new_repo commit-cleanup-attacker-dir)"; P="$(new_plan "$R" auth)"
CLEANUP_ATTACK_HOOK="$TMPROOT/replace-temp-files-with-directories"
cat >"$CLEANUP_ATTACK_HOOK" <<'EOF'
#!/usr/bin/env bash
set -eu
for candidate in "$TMPDIR"/*; do
  [ -f "$candidate" ] || continue
  [ ! -s "$candidate" ] || continue
  rm -f "$candidate"
  mkdir "$candidate"
done
true
EOF
chmod +x "$CLEANUP_ATTACK_HOOK"
RD="$(run_task "$R" "$P" T1)"
ATTACKER_TMP="$TMPROOT/commit-cleanup-attacker"; mkdir -p "$ATTACKER_TMP"
out="$(timeout 30 env TMPDIR="$ATTACKER_TMP" \
  CODEX_COMMIT_TEST_BEFORE_PUBLISH="$CLEANUP_ATTACK_HOOK" \
  "$S/codex_commit.sh" "$P" T1 "$R" "$RD" 2>&1)"
rc=$?
[ "$rc" -eq 124 ] && bad "attacker-directory cleanup does not hang" || ok "attacker-directory cleanup does not hang"
commit_lock="$(git -C "$R" rev-parse --git-path codex-orchestration-commit.lock)"
[ -e "$commit_lock" ] && bad "attacker directory made cleanup skip the commit lock" || ok "attacker directory cannot block lock release"
attacker_dirs="$(find "$ATTACKER_TMP" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d '[:space:]')"
[ "$attacker_dirs" -gt 0 ] && ok "cleanup does not recursively delete attacker-replaced directories" || bad "attacker-replaced directories were unexpectedly removed"

echo "== commit gate records exactly one bounded commit =="
R="$(new_repo commit-green)"; P="$(new_plan "$R" auth)"; RD="$(run_task "$R" "$P" T1)"; before="$(ncommits "$R")"
out="$("$S/codex_commit.sh" "$P" T1 "$R" "$RD" 2>&1)"; rc=$?
check "green task commits" "$rc" "0"
check "exactly one commit" "$(ncommits "$R")" "$((before + 1))"
body="$(git -C "$R" log -1 --format=%B)"
has "task trailer" "$body" "Codex-Task: T1"
has "plan trailer" "$body" "Codex-Plan: auth-"
has "subject comes from task" "$(git -C "$R" log -1 --format=%s)" "Add the token model"
[ -s "$RD/commit.log" ] && ok "commit evidence is written" || bad "missing commit evidence"
check "committed worktree clean" "$(git -C "$R" status --porcelain)" ""
files="$(git -C "$R" show --name-only --format= HEAD)"
has "product path committed" "$files" "src/a.py"
has "active task plan committed" "$files" ".codex-instructions/auth/T1.md"

R="$(new_repo commit-isolation)"; P="$(new_plan "$R" auth)"; mkdir -p "$R/.codex-instructions/other"; printf 'other\n' >"$R/.codex-instructions/other/scratch.md"; RD="$(run_task "$R" "$P" T1)"
out="$("$S/codex_commit.sh" "$P" T1 "$R" "$RD" 2>&1)"; rc=$?
check "active task commits with unrelated metadata present" "$rc" "0"
files="$(git -C "$R" show --name-only --format= HEAD)"
hasnt "other plan is never staged" "$files" "other/scratch.md"
has "other plan remains uncommitted" "$(git -C "$R" status --porcelain)" ".codex-instructions/other/"

echo "== passing tests cannot inject the shared index =="
R="$(new_repo commit-test-stages-meta)"; P="$(new_plan "$R" auth)"
printf 'mkdir -p .codex-instructions/other; printf injected >.codex-instructions/other/injected.md; git add .codex-instructions/other/injected.md\n' >"$P/test"
RD="$(run_task "$R" "$P" T1)"
out="$("$S/codex_commit.sh" "$P" T1 "$R" "$RD" 2>&1)"; rc=$?
check "task commits despite test-staged unrelated metadata" "$rc" "0"
files="$(git -C "$R" show --name-only --format= HEAD)"
has "isolated candidate includes product path" "$files" "src/a.py"
has "isolated candidate includes active plan" "$files" ".codex-instructions/auth/T1.md"
hasnt "test-staged metadata is excluded from candidate" "$files" ".codex-instructions/other/injected.md"
staged_after="$(git -C "$R" diff --cached --name-only)"
has "unrelated staged metadata remains visible after publication" "$staged_after" ".codex-instructions/other/injected.md"

echo "== pre-staged work is refused =="
R="$(new_repo commit-staged-meta)"; P="$(new_plan "$R" auth)"; RD="$(run_task "$R" "$P" T1)"; before="$(ncommits "$R")"
mkdir -p "$R/.codex-instructions/other"; printf 'other\n' >"$R/.codex-instructions/other/scratch.md"
git -C "$R" add .codex-instructions/other/scratch.md
out="$("$S/codex_commit.sh" "$P" T1 "$R" "$RD" 2>&1)"; rc=$?
check "pre-staged other-plan metadata is refused" "$rc" "2"
has "staged-index diagnostic" "$out" "index"
check "staged metadata makes no commit" "$(ncommits "$R")" "$before"

R="$(new_repo commit-staged-product)"; P="$(new_plan "$R" auth)"; RD="$(run_task "$R" "$P" T1)"; before="$(ncommits "$R")"
printf 'unrelated\n' >"$R/docs/d.md"; git -C "$R" add docs/d.md
out="$("$S/codex_commit.sh" "$P" T1 "$R" "$RD" 2>&1)"; rc=$?
check "pre-staged product path is refused" "$rc" "2"
check "staged product makes no commit" "$(ncommits "$R")" "$before"

echo "== commit message and post-test races fail closed =="
R="$(new_repo commit-forged-subject)"; P="$(new_plan "$R" auth)"; RD="$(run_task "$R" "$P" T1)"; before="$(ncommits "$R")"
forged_subject=$'safe-looking subject\n\nCodex-Plan: forged\nCodex-Task: T2'
out="$(CODEX_COMMIT_MESSAGE="$forged_subject" "$S/codex_commit.sh" "$P" T1 "$R" "$RD" 2>&1)"; rc=$?
check "control characters in commit subject are refused" "$rc" "2"
has "subject diagnostic" "$out" "control"
check "forged subject makes no commit" "$(ncommits "$R")" "$before"

R="$(new_repo commit-head-after-test)"; P="$(new_plan "$R" auth)"; printf 'git add -A && git commit -qm moved-by-test\n' >"$P/test"; RD="$(run_task "$R" "$P" T1)"
out="$("$S/codex_commit.sh" "$P" T1 "$R" "$RD" 2>&1)"; rc=$?
check "HEAD movement by a passing test is refused" "$rc" "5"
has "post-test HEAD diagnostic" "$out" "HEAD moved"

echo "== publication is compare-and-swap =="
R="$(new_repo commit-publication-race)"; P="$(new_plan "$R" auth)"; RD="$(run_task "$R" "$P" T1)"; before="$(ncommits "$R")"
race_hook="$TMPROOT/advance-ref-before-publish"
cat >"$race_hook" <<EOF
#!/usr/bin/env bash
git -C "$R" add -A
git -C "$R" commit -qm competing-publisher
EOF
chmod +x "$race_hook"
out="$(CODEX_COMMIT_TEST_BEFORE_PUBLISH="$race_hook" "$S/codex_commit.sh" "$P" T1 "$R" "$RD" 2>&1)"; rc=$?
check "publication race is refused without overwrite" "$rc" "5"
has "publication conflict diagnostic" "$out" "publication"
hasnt "branch race does not claim a task commit" "$out" "T1 committed "
check "race leaves only the competing commit published" "$(ncommits "$R")" "$((before + 1))"
check "competing commit remains HEAD" "$(git -C "$R" log -1 --format=%s)" "competing-publisher"

R="$(new_repo commit-head-repoint-race)"; P="$(new_plan "$R" auth)"; RD="$(run_task "$R" "$P" T1)"; base="$(git -C "$R" rev-parse HEAD)"
git -C "$R" branch other "$base"
repoint_hook="$TMPROOT/repoint-head-before-publish"
cat >"$repoint_hook" <<EOF
#!/usr/bin/env bash
git -C "$R" symbolic-ref HEAD refs/heads/other
EOF
chmod +x "$repoint_hook"
out="$(CODEX_COMMIT_TEST_BEFORE_PUBLISH="$repoint_hook" "$S/codex_commit.sh" "$P" T1 "$R" "$RD" 2>&1)"; rc=$?
check "HEAD repoint after candidate creation still publishes the pinned branch" "$rc" "0"
has "HEAD repoint publication names the pinned branch" "$out" "to refs/heads/work"
has "original pinned task branch carries the candidate" "$(git -C "$R" log -1 --format=%B refs/heads/work)" "Codex-Task: T1"
check "competing branch remains at the frozen base" "$(git -C "$R" rev-parse refs/heads/other)" "$base"
check "HEAD remains on the externally selected branch" "$(git -C "$R" symbolic-ref -q HEAD)" "refs/heads/other"
check "publication evidence records the pinned branch" "$(cat "$RD/commit.ref")" "refs/heads/work"
out="$("$S/codex_status.sh" "$P" "$R" 2>&1)"; rc=$?
check "repointed current branch does not misreport the other branch's task" "$rc" "3"
has "repointed current branch status remains zero" "$out" "0/2 committed"

R="$(new_repo commit-pinned-ref-symref-race)"; P="$(new_plan "$R" auth)"; RD="$(run_task "$R" "$P" T1)"; base="$(git -C "$R" rev-parse HEAD)"
git -C "$R" branch redirect "$base"
symref_hook="$TMPROOT/repoint-pinned-ref-before-publish"
cat >"$symref_hook" <<EOF
#!/usr/bin/env bash
git -C "$R" symbolic-ref refs/heads/work refs/heads/redirect
EOF
chmod +x "$symref_hook"
out="$(CODEX_COMMIT_TEST_BEFORE_PUBLISH="$symref_hook" "$S/codex_commit.sh" "$P" T1 "$R" "$RD" 2>&1)"; rc=$?
check "pinned branch becoming a symref is refused" "$rc" "5"
has "pinned-ref symref race reports publication conflict" "$out" "publication"
hasnt "pinned-ref symref race never reports success" "$out" "T1 committed "
check "redirect target remains at frozen base" "$(git -C "$R" rev-parse refs/heads/redirect)" "$base"
check "pinned branch remains an external symref" "$(git -C "$R" symbolic-ref refs/heads/work)" "refs/heads/redirect"
hasnt "redirect target has no task commit" "$(git -C "$R" log -1 --format=%B refs/heads/redirect)" "Codex-Task: T1"

R="$(new_repo commit-detached-head)"; P="$(new_plan "$R" auth)"; git -C "$R" checkout -q --detach; RD="$(run_task "$R" "$P" T1)"
out="$("$S/codex_commit.sh" "$P" T1 "$R" "$RD" 2>&1)"; rc=$?
check "detached HEAD is refused before publication" "$rc" "2"
has "detached HEAD diagnostic" "$out" "symbolic"

R="$(new_repo commit-unresolvable-head)"; P="$(new_plan "$R" auth)"; RD="$(run_task "$R" "$P" T1)"; base="$(git -C "$R" rev-parse HEAD)"
git -C "$R" reset --mixed -q "$base"
git -C "$R" update-ref refs/heads/unresolvable "$base"
git -C "$R" symbolic-ref HEAD refs/heads/unresolvable
git -C "$R" update-ref -d refs/heads/unresolvable
out="$("$S/codex_commit.sh" "$P" T1 "$R" "$RD" 2>&1)"; rc=$?
check "unresolvable symbolic HEAD is refused" "$rc" "2"
has "unresolvable HEAD diagnostic" "$out" "does not resolve"

echo "== newline paths stay one staged path =="
R="$(new_repo commit-newline-path)"; P="$(new_plan "$R" auth)"; RD="$(run_task "$R" "$P" T1)"
newline_path=$'src/newline\nname.py'; printf 'newline\n' >"$R/$newline_path"
mapfile -d '' -t untracked_before < <(git -C "$R" ls-files --others --exclude-standard -z)
newline_git_path=""
for untracked_path in "${untracked_before[@]}"; do
  case "$untracked_path" in src/*) [ "$untracked_path" = src/a.py ] || newline_git_path="$untracked_path" ;; esac
done
[ -n "$newline_git_path" ] || { bad "newline path is visible to Git before commit"; newline_git_path="$newline_path"; }
out="$("$S/codex_commit.sh" "$P" T1 "$R" "$RD" 2>&1)"; rc=$?
check "newline product path commits" "$rc" "0"
newline_names="$TMPROOT/newline-committed-names"
git -C "$R" ls-tree -r -z --name-only HEAD >"$newline_names"; rc=$?
check "newline object listing succeeds" "$rc" "0"
mapfile -d '' -t committed_paths <"$newline_names"
newline_found=false
for committed_path in "${committed_paths[@]}"; do
  [ "$committed_path" = "$newline_git_path" ] && newline_found=true
done
check "newline product path exactly matches a committed object name" "$newline_found" "true"

echo "== Git pathspec syntax is always treated literally =="
R="$(new_repo commit-bracket-path)"; P="$(new_plan "$R" auth)"; RD="$(run_task "$R" "$P" T1)"
bracket_path='src/[magic].py'; printf 'literal brackets\n' >"$R/$bracket_path"
out="$("$S/codex_commit.sh" "$P" T1 "$R" "$RD" 2>&1)"; rc=$?
check "bracket path commits literally" "$rc" "0"
bracket_names="$TMPROOT/bracket-committed-names"
git -C "$R" ls-tree -r -z --name-only HEAD >"$bracket_names"
mapfile -d '' -t committed_paths <"$bracket_names"
bracket_found=false
for committed_path in "${committed_paths[@]}"; do
  [ "$committed_path" = "$bracket_path" ] && bracket_found=true
done
check "bracket path exactly matches a committed object name" "$bracket_found" "true"

R="$(new_repo commit-posix-magic-path)"; P="$(new_plan "$R" auth)"
printf 'src/*\n:(literal)magic.py\n' >"$P/T1.allowlist"
RD="$(run_task "$R" "$P" T1)"
magic_path=':(literal)magic.py'
magic_error="$TMPROOT/posix-magic-create.err"
if printf 'literal pathspec magic\n' >"$R/$magic_path" 2>"$magic_error"; then
  mapfile -d '' -t magic_untracked < <(git -C "$R" ls-files --others --exclude-standard -z)
  magic_visible=false
  for untracked_path in "${magic_untracked[@]}"; do
    [ "$untracked_path" = "$magic_path" ] && magic_visible=true
  done
  if [ "$magic_visible" = "true" ]; then
    out="$("$S/codex_commit.sh" "$P" T1 "$R" "$RD" 2>&1)"; rc=$?
    check "POSIX pathspec-magic filename commits literally" "$rc" "0"
    magic_names="$TMPROOT/magic-committed-names"
    git -C "$R" ls-tree -r -z --name-only HEAD >"$magic_names"
    mapfile -d '' -t committed_paths <"$magic_names"
    magic_found=false
    for committed_path in "${committed_paths[@]}"; do
      [ "$committed_path" = "$magic_path" ] && magic_found=true
    done
    check "POSIX pathspec-magic name exactly matches the committed object" "$magic_found" "true"
  else
    ok "POSIX pathspec-magic regression skipped: Git cannot round-trip the exact ':' filename on this filesystem"
  fi
else
  ok "POSIX pathspec-magic regression skipped: filesystem rejected ':' ($(tr '\n' ' ' <"$magic_error"))"
fi

echo "== test gate policy =="
R="$(new_repo commit-no-test)"; P="$(new_plan "$R" auth)"; rm "$P/test"; RD="$(run_task "$R" "$P" T1)"
out="$("$S/codex_commit.sh" "$P" T1 "$R" "$RD" 2>&1)"; rc=$?
check "missing tests fail closed" "$rc" "2"
out="$(CODEX_ALLOW_NO_TESTS=1 "$S/codex_commit.sh" "$P" T1 "$R" "$RD" 2>&1)"; rc=$?
check "explicit no-test override commits" "$rc" "0"

R="$(new_repo commit-task-test)"; P="$(new_plan "$R" auth)"; printf 'false\n' >"$P/test"; printf 'true\n' >"$P/T1.test"; RD="$(run_task "$R" "$P" T1)"
out="$("$S/codex_commit.sh" "$P" T1 "$R" "$RD" 2>&1)"; rc=$?
check "per-task frozen test overrides default" "$rc" "0"

echo "== commit architecture keeps no authoritative path snapshots across tests =="
commit_source="$(cat "$S/codex_commit.sh")"
hasnt "commit gate has no persistent pre-test product-list pathname" "$commit_source" "PRODUCT_LIST_BEFORE"
hasnt "commit gate has no persistent post-test product-list pathname" "$commit_source" "PRODUCT_LIST_AFTER"
hasnt "commit gate never reparses the mutable run allowlist" "$commit_source" 'codex_load_allowlist "$RUNDIR/allowlist"'
hasnt "commit gate has no Git-metadata allowlist snapshot" "$commit_source" "allowlist.XXXXXX"
has "cleanup makes each temp-file removal independently best-effort" "$commit_source" 'rm -f -- "$path" 2>/dev/null || true'

echo "== status reports git-backed evidence =="
R="$(new_repo status)"; P="$(new_plan "$R" auth)"
out="$("$S/codex_status.sh" "$P" "$R" 2>&1)"; rc=$?
check "remaining tasks return 3" "$rc" "3"
has "first task is next" "$out" "<- next"
has "initial count" "$out" "0/2 committed"
has "status displays plan identity" "$out" "[auth-"

RD="$(run_task "$R" "$P" T1)"; "$S/codex_commit.sh" "$P" T1 "$R" "$RD" >/dev/null 2>&1
out="$("$S/codex_status.sh" "$P" "$R" 2>&1)"; rc=$?
check "tasks remain after first commit" "$rc" "3"
has "first task is proven done" "$out" "T1   done"
has "partial count" "$out" "1/2 committed"

RD="$(run_task "$R" "$P" T2)"; "$S/codex_commit.sh" "$P" T2 "$R" "$RD" >/dev/null 2>&1
out="$("$S/codex_status.sh" "$P" "$R" 2>&1)"; rc=$?
check "complete plan returns 0" "$rc" "0"
has "complete count" "$out" "2/2 committed"

printf 'mid-flight\n' >>"$R/src/a.py"; out="$("$S/codex_status.sh" "$P" "$R" 2>&1)"
has "dirty worktree is evidence" "$out" "worktree dirty"

P2="$(new_plan "$R" billing)"; out="$("$S/codex_status.sh" "$P2" "$R" 2>&1)"; rc=$?
check "different plan identity starts at zero" "$rc" "3"
has "different plan count" "$out" "0/2 committed"

R="$(new_repo status-forged-trailer)"; P="$(new_plan "$R" auth)"
printf 'forged\n' >"$R/src/a.py"; git -C "$R" add src/a.py
cat >"$R/message" <<EOF
Forged evidence

Codex-Plan: $(cat "$P/plan-id")
Codex-Task: T1

This prose makes the preceding lines non-canonical trailers.
EOF
git -C "$R" commit -q -F message
out="$("$S/codex_status.sh" "$P" "$R" 2>&1)"; rc=$?
check "non-canonical forged trailers do not mark work done" "$rc" "3"
has "forged-trailer count remains zero" "$out" "0/2 committed"

R="$(new_repo status-order)"; P="$(new_plan "$R" auth)"
for n in 3 10; do printf '# task %s\n' "$n" >"$P/T$n.md"; done
order="$("$S/codex_status.sh" "$P" "$R" 2>&1 | sed -n 's/^  \(T[0-9]*\) .*/\1/p' | tr '\n' ' ')"
check "tasks are numeric ordered" "$order" "T1 T2 T3 T10 "
rm -f "$P"/T*.md
out="$("$S/codex_status.sh" "$P" "$R" 2>&1)"; rc=$?
check "empty plan is rejected" "$rc" "2"

finish
