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

echo "== newline paths stay one staged path =="
R="$(new_repo commit-newline-path)"; P="$(new_plan "$R" auth)"; RD="$(run_task "$R" "$P" T1)"
newline_path=$'src/newline\nname.py'; printf 'newline\n' >"$R/$newline_path"
out="$("$S/codex_commit.sh" "$P" T1 "$R" "$RD" 2>&1)"; rc=$?
check "newline product path commits" "$rc" "0"
git -C "$R" ls-tree -z HEAD -- "$newline_path" >/dev/null; rc=$?
check "newline product path is present in the commit" "$rc" "0"

echo "== test gate policy =="
R="$(new_repo commit-no-test)"; P="$(new_plan "$R" auth)"; rm "$P/test"; RD="$(run_task "$R" "$P" T1)"
out="$("$S/codex_commit.sh" "$P" T1 "$R" "$RD" 2>&1)"; rc=$?
check "missing tests fail closed" "$rc" "2"
out="$(CODEX_ALLOW_NO_TESTS=1 "$S/codex_commit.sh" "$P" T1 "$R" "$RD" 2>&1)"; rc=$?
check "explicit no-test override commits" "$rc" "0"

R="$(new_repo commit-task-test)"; P="$(new_plan "$R" auth)"; printf 'false\n' >"$P/test"; printf 'true\n' >"$P/T1.test"; RD="$(run_task "$R" "$P" T1)"
out="$("$S/codex_commit.sh" "$P" T1 "$R" "$RD" 2>&1)"; rc=$?
check "per-task frozen test overrides default" "$rc" "0"

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
