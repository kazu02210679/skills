#!/usr/bin/env bash
# Report a plan's progress exclusively from its commit-trailer evidence.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=codex_lib.sh
. "$SCRIPT_DIR/codex_lib.sh"

die() { printf 'codex_status: %s\n' "$1" >&2; exit 2; }
[ "$#" -eq 2 ] || die "usage: codex_status.sh <taskdir> <workdir>"
TASKDIR="$1"; WORKDIR="$2"
[ -d "$TASKDIR" ] || die "task directory not found: $TASKDIR"
[ -d "$WORKDIR" ] || die "workdir not found: $WORKDIR"
git -C "$WORKDIR" rev-parse --is-inside-work-tree >/dev/null 2>&1 || die "not a git repository: $WORKDIR"
TASKDIR_ABS="$(cd -- "$TASKDIR" && pwd)"

ids=()
while IFS= read -r id; do [ -n "$id" ] && ids+=("$id"); done < <(
  for task_file in "$TASKDIR_ABS"/T*.md; do
    [ -f "$task_file" ] || continue
    base="$(basename "$task_file" .md)"; number="${base#T}"
    case "$number" in ''|*[!0-9]*) continue ;; esac
    printf '%s\t%s\n' "$number" "$base"
  done | LC_ALL=C sort -n | cut -f2
)
[ "${#ids[@]}" -gt 0 ] || die "no T<N>.md task packets in $TASKDIR"
PLAN_ID="$(codex_plan_id "$TASKDIR_ABS")"
[ -n "$PLAN_ID" ] || die "plan identity is empty"

# Never swallow a Git history failure: an incomplete ledger cannot prove done.
history="$(mktemp)" || die "could not create a history file"
trap 'rm -f "$history"' EXIT
if ! git -C "$WORKDIR" log --format='%h%x1f%s%x1f%b%x1e' >"$history"; then
  die "could not read Git commit history"
fi
declare -A sha_of=() subject_of=()
while IFS= read -r -d $'\x1e' rec; do
  rec="${rec#"${rec%%[![:space:]]*}"}"; [ -n "$rec" ] || continue
  sha="${rec%%$'\x1f'*}"; rest="${rec#*$'\x1f'}"
  subject="${rest%%$'\x1f'*}"; body="${rest#*$'\x1f'}"
  # Only the final paragraph can be a canonical trailer block. This avoids
  # treating lookalike lines in commit prose as evidence of task completion.
  while [[ "$body" == *$'\n' ]]; do body="${body%$'\n'}"; done
  trailers="${body##*$'\n\n'}"
  plans=(); tasks=()
  while IFS= read -r trailer; do
    case "$trailer" in
      Codex-Plan:*) plans+=("${trailer#Codex-Plan: }") ;;
      Codex-Task:*) tasks+=("${trailer#Codex-Task: }") ;;
    esac
  done <<<"$trailers"
  [ "${#plans[@]}" -eq 1 ] && [ "${#tasks[@]}" -eq 1 ] || continue
  plan="${plans[0]}"; task="${tasks[0]}"
  [ "$plan" = "$PLAN_ID" ] && [[ "$task" =~ ^[A-Za-z0-9_-]+$ ]] && [ -z "${sha_of[$task]:-}" ] && {
    sha_of[$task]="$sha"; subject_of[$task]="$subject";
  }
done <"$history"

printf 'plan: %s [%s] (%d task(s))\n' "$TASKDIR" "$PLAN_ID" "${#ids[@]}"
done_count=0; next=""
for id in "${ids[@]}"; do
  title="$(grep -m1 '^# ' "$TASKDIR_ABS/$id.md" 2>/dev/null | sed 's/^# *//' || true)"
  if [ -n "${sha_of[$id]:-}" ]; then
    done_count=$((done_count + 1))
    printf '  %-4s done     %-9s %s\n' "$id" "${sha_of[$id]}" "${subject_of[$id]}"
  elif [ -z "$next" ]; then
    next="$id"; printf '  %-4s pending  %-9s %s   <- next\n' "$id" '' "$title"
  else
    printf '  %-4s pending  %-9s %s\n' "$id" '' "$title"
  fi
done
dirty="$(git -C "$WORKDIR" status --porcelain)" || die "could not read worktree status"
[ -z "$dirty" ] || dirty=' (worktree dirty — a task is mid-flight)'
printf '%d/%d committed%s\n' "$done_count" "${#ids[@]}" "$dirty"
[ "$done_count" -eq "${#ids[@]}" ] && exit 0
exit 3
