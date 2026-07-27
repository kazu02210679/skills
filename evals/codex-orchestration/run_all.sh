#!/usr/bin/env bash
# Run every codex-orchestration shell evaluation in isolated disposable repos.
set -uo pipefail

# Git for Windows can inherit a Windows-only PATH when launched directly from
# PowerShell, before lib.sh has a chance to normalize it.
export PATH="/usr/bin:/bin:$PATH"
cd -- "$(dirname -- "${BASH_SOURCE[0]}")" || exit 2

failed=()
for test_file in test_*.sh; do
  printf '\n### %s\n' "$test_file"
  bash "$test_file" || failed+=("$test_file")
done

printf '\n=========================================\n'
if [ "${#failed[@]}" -eq 0 ]; then
  printf 'all suites passed\n'
  exit 0
fi
printf 'FAILED: %s\n' "${failed[*]}"
exit 1
