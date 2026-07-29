#!/usr/bin/env bash
# Frozen-contract and cross-platform path regressions.
set -uo pipefail
. "$(dirname "$0")/lib.sh"

echo "== an explicit sort-path selection survives library loading =="
selected_sort_path() {
  (
    export CODEX_SORT0="$1"
    . "$S/codex_lib.sh"
    codex_sort0_available >/dev/null 2>&1
    printf '%s' "$CODEX_SORT0"
  )
}
check "CODEX_SORT0=1 selects the sort -z path" "$(selected_sort_path 1)" "1"
check "CODEX_SORT0=0 selects the portable fallback" "$(selected_sort_path 0)" "0"

R="$(new_repo review-sort-agreement)"; P="$(new_plan "$R" sort)"
mkdir -p "$R/src/deep" "$P/sub"
for name in b a 'z z' 'a-b' 'a_b' 'A' '10' '2' $'x\ny'; do
  printf 'x\n' >"$R/src/deep/$name"
done
for name in b a 'z z' 'A'; do printf 'x\n' >"$P/sub/$name"; done
sorted_with() {
  (
    export CODEX_SORT0="$1"
    . "$S/codex_lib.sh"
    codex_dirty_product "$R" HEAD
  )
}
fingerprint_with() {
  (
    export CODEX_SORT0="$1"
    . "$S/codex_lib.sh"
    codex_meta_fingerprint "$P"
  )
}
fallback="$(sorted_with 0)"; fallback_rc=$?
check "forced fallback listing succeeds" "$fallback_rc" "0"
if command -v sort >/dev/null 2>&1 &&
   [ "$(printf 'b\0a\0' | LC_ALL=C sort -z 2>/dev/null | tr '\0' ',')" = "a,b," ]; then
  fast="$(sorted_with 1)"; fast_rc=$?
  check "forced sort -z listing succeeds" "$fast_rc" "0"
  check "forced sort paths produce identical ordering" "$fast" "$fallback"
  check "forced sort paths produce identical fingerprints" \
    "$(fingerprint_with 1)" "$(fingerprint_with 0)"
else
  ok "forced sort -z comparison skipped: sort -z is unavailable"
fi

echo "== resume authenticates the recorded live allowlist before Codex =="
R="$(new_repo review-resume-drift)"; P="$(new_plan "$R" auth)"
mv "$P/T1.allowlist" "$P/shared.allowlist"
CODEX_ALLOWLIST="$P/shared.allowlist" FAKE_CODEX_TOUCH="src/a.py" \
  "$S/codex_run.sh" "$P/T1.md" "$R" >/dev/null 2>&1
RD="$(rundir_of "$R")"; printf 'hint\n' >"$P/T1.hint-1.md"
original_allowlist="$(cat "$P/shared.allowlist")"

printf 'docs/*\n' >"$P/shared.allowlist"
LOG="$TMPROOT/review-changed-allowlist"; : >"$LOG"
out="$(CODEX_ALLOWLIST="$P/shared.allowlist" FAKE_CODEX_LOG="$LOG" \
  "$S/codex_resume.sh" "$P/T1.hint-1.md" "$R" "$RD" 2>&1)"; rc=$?
check "changed recorded allowlist is contract drift" "$rc" "4"
has "changed allowlist refusal identifies the source" "$out" "allowlist"
check "changed recorded allowlist launches nothing" "$(grep -c '^ARGV:' "$LOG")" "0"
[ -d "$RD/attempt-2" ] \
  && bad "changed allowlist consumed attempt-2" \
  || ok "changed allowlist consumes no attempt"

printf '%s\n' "$original_allowlist" >"$P/shared.allowlist"
out="$(CODEX_ALLOWLIST="$P/shared.allowlist" FAKE_CODEX_TOUCH="src/a.py" \
  "$S/codex_resume.sh" "$P/T1.hint-1.md" "$R" "$RD" 2>&1)"; rc=$?
check "restoring the allowlist permits the same run to resume" "$rc" "0"
[ -d "$RD/attempt-2" ] \
  && ok "restored allowlist creates attempt-2" \
  || bad "restored allowlist did not create attempt-2"

R="$(new_repo review-resume-missing)"; P="$(new_plan "$R" auth)"
mv "$P/T1.allowlist" "$P/shared.allowlist"
CODEX_ALLOWLIST="$P/shared.allowlist" FAKE_CODEX_TOUCH="src/a.py" \
  "$S/codex_run.sh" "$P/T1.md" "$R" >/dev/null 2>&1
RD="$(rundir_of "$R")"; printf 'hint\n' >"$P/T1.hint-1.md"
rm -f "$P/shared.allowlist"
LOG="$TMPROOT/review-missing-allowlist"; : >"$LOG"
out="$(CODEX_ALLOWLIST="$P/shared.allowlist" FAKE_CODEX_LOG="$LOG" \
  "$S/codex_resume.sh" "$P/T1.hint-1.md" "$R" "$RD" 2>&1)"; rc=$?
check "deleted recorded allowlist is contract drift" "$rc" "4"
has "deleted allowlist refusal identifies the source" "$out" "allowlist"
check "deleted recorded allowlist launches nothing" "$(grep -c '^ARGV:' "$LOG")" "0"
[ -d "$RD/attempt-2" ] \
  && bad "deleted allowlist consumed attempt-2" \
  || ok "deleted allowlist consumes no attempt"

echo "== Git common-directory paths are normalized without rewriting POSIX paths =="
. "$S/codex_lib.sh"
relative_repo="$(new_repo review-relative-gitdir)"
expected_relative="$(cd "$relative_repo/.git" && pwd)"
check "relative .git resolves against the worktree" \
  "$(codex_normalize_git_path "$relative_repo" .git)" "$expected_relative"
check "Linux/macOS absolute paths are preserved" \
  "$(codex_normalize_git_path "$relative_repo" /var/tmp/example.git)" \
  "/var/tmp/example.git"
check "Git Bash drive-mount paths are preserved" \
  "$(codex_normalize_git_path "$relative_repo" '/c/Users/Test Space/日本/.git')" \
  "/c/Users/Test Space/日本/.git"

drive_path='C:/Users/Test Space/日本/.git'
if command -v cygpath >/dev/null 2>&1; then
  expected_drive="$(cygpath -u "$drive_path")"
  check "Windows drive paths use cygpath when available" \
    "$(codex_normalize_git_path "$relative_repo" "$drive_path")" "$expected_drive"
else
  ok "cygpath conversion unavailable on this platform"
fi
empty_path="$TMPROOT/no-cygpath-bin"; mkdir -p "$empty_path"
check "Windows drive paths are preserved when cygpath is unavailable" \
  "$(PATH="$empty_path" codex_normalize_git_path "$relative_repo" "$drive_path")" \
  "$drive_path"

echo "== normal and linked worktrees can anchor and run =="
R="$(new_repo 'review normal space 日本')"; P="$(new_plan "$R" normal)"
out="$(FAKE_CODEX_TOUCH="src/a.py" "$S/codex_run.sh" "$P/T1.md" "$R" 2>&1)"; rc=$?
check "normal worktree run succeeds" "$rc" "0"
RD="$(rundir_of "$R")"
anchor="$(codex_contract_anchor "$R" "$RD")"; anchor_rc=$?
check "normal worktree anchor resolves" "$anchor_rc" "0"
[ -f "$anchor" ] && ok "normal worktree anchor exists" || bad "normal worktree anchor missing: $anchor"

PRIMARY="$(new_repo review-linked-primary)"
LINKED="$TMPROOT/linked space 日本"
git -C "$PRIMARY" worktree add -q -b linked-review "$LINKED" HEAD
P="$(new_plan "$LINKED" linked)"
out="$(FAKE_CODEX_TOUCH="src/a.py" "$S/codex_run.sh" "$P/T1.md" "$LINKED" 2>&1)"; rc=$?
check "linked worktree run succeeds" "$rc" "0"
RD="$(rundir_of "$LINKED")"
anchor="$(codex_contract_anchor "$LINKED" "$RD")"; anchor_rc=$?
check "linked worktree anchor resolves" "$anchor_rc" "0"
[ -f "$anchor" ] && ok "linked worktree anchor exists" || bad "linked worktree anchor missing: $anchor"

finish
