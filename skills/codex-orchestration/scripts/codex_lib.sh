#!/usr/bin/env bash
#
# codex_lib.sh — shared helpers. Sourced, never executed.
#
# The important idea here is the split between two kinds of file:
#
#   product files       what Codex is asked to change. Governed by the task's
#                       allowlist, and the thing the diff review is about.
#   orchestration meta  the plan, hints, interfaces, run artifacts. Written by
#                       the orchestrator, changes constantly during the loop,
#                       and is not part of the product diff.
#
# Holding both to one rule is what made "keep the plan in version control",
# "refuse to start from a dirty tree" and "write a hint file mid-loop"
# contradict each other. Meta paths are excluded from the dirty preflight and
# from the scope gate, and are instead protected by a fingerprint taken across
# each Codex run: the orchestrator may write there between runs, Codex may
# never write there at all.

# bash 4.4+: NUL-delimited mapfile (-d) and `declare -A` are both load-bearing.
if [ -z "${BASH_VERSINFO:-}" ] ||
   [ "${BASH_VERSINFO[0]}" -lt 4 ] ||
   { [ "${BASH_VERSINFO[0]}" -eq 4 ] && [ "${BASH_VERSINFO[1]}" -lt 4 ]; }; then
  printf 'codex: bash 4.4+ required, found %s. On macOS: brew install bash.\n' \
    "${BASH_VERSION:-unknown}" >&2
  exit 2
fi

# Workdir-relative paths that are orchestration metadata, never product.
CODEX_META_DIR="${CODEX_META_DIR:-.codex-instructions}"
CODEX_RUNS_DIR="${CODEX_RUNS_DIR:-.codex-runs}"

# codex_is_meta_path <path>
# True when a workdir-relative path is orchestration metadata.
codex_is_meta_path() {
  case "$1" in
    "$CODEX_META_DIR"/*|"$CODEX_META_DIR") return 0 ;;
    "$CODEX_RUNS_DIR"/*|"$CODEX_RUNS_DIR") return 0 ;;
    *) return 1 ;;
  esac
}

# codex_load_allowlist <file> <array_name>
# Parse one allowlist into caller-owned memory. A commit gate keeps this array
# in its parent shell while tests run in children, so tests have no pathname
# they can rewrite to change the verdict.
codex_load_allowlist() {
  local file="$1" output_name="$2" line
  local -n output="$output_name"
  output=()
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line%%#*}"
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    [ -n "$line" ] && output+=("$line")
  done <"$file"
  return 0
}

# codex_path_allowed <literal_path> <pattern>...
# The path is always data. Only allowlist entries are intentional Bash globs.
codex_path_allowed() {
  local path="$1" pattern
  shift
  for pattern in "$@"; do
    # shellcheck disable=SC2053  # allowlist entries intentionally are globs
    [[ "$path" == $pattern ]] && return 0
  done
  return 1
}

# codex_dirty_product <workdir> [base_ref]
# Changed PRODUCT paths, one per line — metadata excluded. Used both by the
# dirty preflight and by the "did this task actually do anything?" check, which
# have to agree: with the plan directory always untracked during a run, a check
# over the whole worktree can never see a clean tree and never sees a task that
# did nothing. Also used to build the staging list, which is why renames are
# expanded rather than detected: `--name-only` reports only a rename's
# destination, so staging from it would leave the source's deletion behind.
codex_dirty_product0() {
  local wd="$1" base="${2:-HEAD}" f tmp key i j
  local -a files=()
  local -A seen=()
  tmp="$(mktemp)" || { printf 'codex: could not create a temporary file for the dirty-product check.\n' >&2; return 2; }
  [ -n "$tmp" ] || { printf 'codex: could not create a temporary file for the dirty-product check.\n' >&2; return 2; }
  if ! git -C "$wd" diff --no-renames --name-only -z "$base" -- >"$tmp" 2>/dev/null; then
    rm -f "$tmp"; printf 'codex: could not determine changed product files from %s.\n' "$wd" >&2; return 2
  fi
  if ! git -C "$wd" ls-files --others --exclude-standard -z >>"$tmp" 2>/dev/null; then
    rm -f "$tmp"; printf 'codex: could not determine untracked product files from %s.\n' "$wd" >&2; return 2
  fi
  while IFS= read -r -d '' f; do
    [ -n "$f" ] || continue
    codex_is_meta_path "$f" || seen["$f"]=1
  done <"$tmp"
  rm -f "$tmp"
  files=("${!seen[@]}")
  for ((i = 1; i < ${#files[@]}; i++)); do
    key="${files[$i]}"; j=$((i - 1))
    while [ "$j" -ge 0 ] && [[ "${files[$j]}" > "$key" ]]; do
      files[$((j + 1))]="${files[$j]}"; j=$((j - 1))
    done
    files[$((j + 1))]="$key"
  done
  for f in "${files[@]}"; do printf '%s\0' "$f"; done
}

codex_dirty_product() {
  local wd="$1" base="${2:-HEAD}" f tmp rc
  tmp="$(mktemp)" || {
    printf 'codex: could not create a temporary file for the dirty-product check.\n' >&2
    return 2
  }
  [ -n "$tmp" ] || {
    printf 'codex: could not create a temporary file for the dirty-product check.\n' >&2
    return 2
  }
  set +e
  codex_dirty_product0 "$wd" "$base" >"$tmp"
  rc=$?
  set -e
  if [ "$rc" -ne 0 ]; then rm -f "$tmp"; return "$rc"; fi
  while IFS= read -r -d '' f; do printf '%s\n' "$f"; done <"$tmp"
  rm -f "$tmp"
}

# codex_plan_id <plandir>
# The plan's stable identity. A directory name is a display label, not an id:
# deleting `.codex-instructions/auth/` and writing a new plan under the same
# name would otherwise inherit the old plan's task commits and report its
# first task as already finished. /codex-spec writes plan-id; the basename is
# only a fallback for plans made before that existed.
codex_plan_id() {
  local d="$1"
  if [ -s "$d/plan-id" ]; then
    tr -d '[:space:]' <"$d/plan-id"
  else
    basename "$(cd -- "$d" && pwd)"
  fi
}

# codex_test_file <plandir> <task_id>
# The test commands that gate this task's commit, or nothing. Per-task file
# wins over the plan default.
codex_test_file() {
  if   [ -f "$1/$2.test" ]; then printf '%s\n' "$1/$2.test"
  elif [ -f "$1/test" ];    then printf '%s\n' "$1/test"
  fi
}

# --- hashing ----------------------------------------------------------------
# sha256sum is GNU coreutils; macOS ships shasum instead. Resolve once, and
# fail loudly rather than silently skipping an integrity check.
#
# All three MUST print the digest as the first space-separated field. Plain
# `openssl dgst -sha256` prints `SHA2-256(stdin)= <hash>`, whose first field is
# a constant — every file would hash alike and the integrity checks would pass
# anything. `-r` switches it to coreutils order. Set CODEX_HASH_CMD to force a
# backend; the tests use it to exercise each one.
CODEX_HASH=()
if [ -n "${CODEX_HASH_CMD:-}" ]; then
  # shellcheck disable=SC2206  # deliberate word splitting: this is a command
  CODEX_HASH=(${CODEX_HASH_CMD})
elif command -v sha256sum >/dev/null 2>&1; then CODEX_HASH=(sha256sum)
elif command -v shasum >/dev/null 2>&1;    then CODEX_HASH=(shasum -a 256)
elif command -v openssl >/dev/null 2>&1;   then CODEX_HASH=(openssl dgst -sha256 -r)
fi

codex_require_hash() {
  [ "${#CODEX_HASH[@]}" -gt 0 ] && return 0
  printf 'codex: no SHA-256 tool found (looked for sha256sum, shasum, openssl).\n' >&2
  printf '  The plan-integrity check cannot run without one.\n' >&2
  return 1
}

# --- JSON encoding ---------------------------------------------------------
# Metadata is evidence, so it must remain valid for every legal path and
# option value. Shell interpolation cannot safely encode quotes, backslashes,
# control characters, or newlines. Prefer Python's standard-library encoder
# and fall back to Perl's core JSON::PP module; fail closed if neither exists.
CODEX_JSON=()
CODEX_JSON_KIND=""

codex_require_json_encoder() {
  local candidate_name
  local -a candidate=()
  [ -n "$CODEX_JSON_KIND" ] && return 0

  if [ -n "${CODEX_JSON_CMD:-}" ]; then
    # shellcheck disable=SC2206  # deliberate word splitting: command override
    candidate=(${CODEX_JSON_CMD})
    if [ "${#candidate[@]}" -gt 0 ] &&
       command -v "${candidate[0]}" >/dev/null 2>&1 &&
       "${candidate[@]}" -c 'import json' >/dev/null 2>&1; then
      CODEX_JSON=("${candidate[@]}")
      CODEX_JSON_KIND=python
      return 0
    fi
    printf 'codex: configured JSON encoder is unavailable or cannot import json: %s\n' \
      "$CODEX_JSON_CMD" >&2
    return 1
  fi

  for candidate_name in python3 python; do
    if command -v "$candidate_name" >/dev/null 2>&1 &&
       "$candidate_name" -c 'import json' >/dev/null 2>&1; then
      CODEX_JSON=("$candidate_name")
      CODEX_JSON_KIND=python
      return 0
    fi
  done
  if command -v perl >/dev/null 2>&1 &&
     perl -MJSON::PP -e 1 >/dev/null 2>&1; then
    CODEX_JSON=(perl)
    CODEX_JSON_KIND=perl
    return 0
  fi

  printf 'codex: no JSON encoder found (looked for Python json and Perl JSON::PP).\n' >&2
  printf '  Run metadata cannot be recorded safely without one.\n' >&2
  return 1
}

# codex_write_json <output> (<key> <string|integer|boolean> <value>)...
codex_write_json() {
  local output="$1" tmp rc
  shift
  [ $(( $# % 3 )) -eq 0 ] || {
    printf 'codex: internal JSON field list is malformed.\n' >&2
    return 1
  }
  codex_require_json_encoder || return 1
  tmp="$output.tmp.$$"
  rm -f "$tmp"
  rc=0
  case "$CODEX_JSON_KIND" in
    python)
      "${CODEX_JSON[@]}" -c '
import json
import sys

path = sys.argv[1]
fields = sys.argv[2:]
value_by_type = {
    "string": lambda value: value,
    "integer": lambda value: int(value),
    "boolean": lambda value: {"true": True, "false": False}[value],
}
result = {}
for index in range(0, len(fields), 3):
    key, kind, value = fields[index:index + 3]
    result[key] = value_by_type[kind](value)
with open(path, "w", encoding="utf-8", newline="\n") as stream:
    json.dump(result, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
' "$tmp" "$@" || rc=$?
      ;;
    perl)
      "${CODEX_JSON[@]}" -MJSON::PP -e '
use strict;
use warnings;
my $path = shift @ARGV;
my %result;
while (@ARGV) {
  my ($key, $kind, $value) = splice @ARGV, 0, 3;
  if ($kind eq "string") {
    $result{$key} = $value;
  } elsif ($kind eq "integer") {
    $result{$key} = 0 + $value;
  } elsif ($kind eq "boolean" && ($value eq "true" || $value eq "false")) {
    $result{$key} = $value eq "true" ? JSON::PP::true : JSON::PP::false;
  } else {
    die "invalid JSON field type or value\n";
  }
}
open my $stream, ">:raw", $path or die "open $path: $!\n";
print {$stream} JSON::PP->new->utf8->pretty->canonical->encode(\%result);
close $stream or die "close $path: $!\n";
' "$tmp" "$@" || rc=$?
      ;;
    *) rc=1 ;;
  esac
  if [ "$rc" -ne 0 ] || [ ! -s "$tmp" ]; then
    rm -f "$tmp"
    printf 'codex: JSON metadata encoding failed for %s.\n' "$output" >&2
    return 1
  fi
  mv "$tmp" "$output" || {
    rm -f "$tmp"
    printf 'codex: could not publish JSON metadata to %s.\n' "$output" >&2
    return 1
  }
}

# codex_hash_file <path> — hash of one file's contents, or the empty string.
codex_hash_file() {
  [ -f "$1" ] || { printf '\n'; return 0; }
  "${CODEX_HASH[@]}" <"$1" | cut -d' ' -f1
}

# codex_contract_anchor <workdir> <rundir>
# Trusted copy of a run contract, kept under Git metadata rather than the
# workspace-writable .codex-runs directory.
codex_contract_anchor() {
  local wd="$1" rundir="$2" gitdir key rundir_abs
  gitdir="$(git -C "$wd" rev-parse --git-common-dir 2>/dev/null)" || return 1
  case "$gitdir" in
    /*|[A-Za-z]:/*) ;;
    *) gitdir="$(cd -- "$wd/$gitdir" && pwd)" || return 1 ;;
  esac
  rundir_abs="$(cd -- "$(dirname -- "$rundir")" && pwd)/$(basename -- "$rundir")" || return 1
  key="$(printf '%s' "$rundir_abs" | "${CODEX_HASH[@]}" | cut -d' ' -f1)" || return 1
  printf '%s/codex-orchestration-contracts/%s.sha256\n' "$gitdir" "$key"
}

# Fixed frozen-contract members. Missing optional members are recorded too, so
# deleting an allowlist or adding a test file is itself a contract mutation.
CODEX_CONTRACT_FILES=(base_commit task.md allowlist test plan_dir plan-id test_source workdir)

# codex_contract_write <rundir> <workdir> <is_git>
codex_contract_write() {
  local rundir="$1" wd="$2" is_git="$3" rel hash manifest anchor tmp
  manifest="$rundir/contract.sha256"
  tmp="$manifest.tmp.$$"
  : >"$tmp" || return 1
  for rel in "${CODEX_CONTRACT_FILES[@]}"; do
    if [ -f "$rundir/$rel" ]; then
      hash="$(codex_hash_file "$rundir/$rel")" || { rm -f "$tmp"; return 1; }
      printf 'F %s %s\n' "$hash" "$rel" >>"$tmp" || { rm -f "$tmp"; return 1; }
    else
      printf 'M - %s\n' "$rel" >>"$tmp" || { rm -f "$tmp"; return 1; }
    fi
  done
  mv "$tmp" "$manifest" || return 1

  [ "$is_git" = "1" ] || return 0
  anchor="$(codex_contract_anchor "$wd" "$rundir")" || return 1
  mkdir -p "$(dirname -- "$anchor")" || return 1
  tmp="$anchor.tmp.$$"
  cp "$manifest" "$tmp" && mv "$tmp" "$anchor"
}

# codex_contract_check <rundir> <workdir> [expected_manifest_hash]
# Git-backed runs compare the visible manifest against the trusted .git copy.
# A one-off non-Git run may pass the in-process manifest hash captured before
# Codex started.
codex_contract_check() {
  local rundir="$1" wd="$2" expected="${3:-}" manifest anchor source
  local kind hash rel actual count=0
  local -A seen=()
  manifest="$rundir/contract.sha256"
  [ -f "$manifest" ] || { printf 'codex: frozen contract manifest is missing.\n' >&2; return 1; }

  if git -C "$wd" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    anchor="$(codex_contract_anchor "$wd" "$rundir")" || {
      printf 'codex: trusted frozen contract anchor cannot be resolved.\n' >&2
      return 1
    }
    [ -f "$anchor" ] || { printf 'codex: trusted frozen contract anchor is missing.\n' >&2; return 1; }
    cmp -s "$manifest" "$anchor" || {
      printf 'codex: frozen contract manifest does not match its trusted anchor.\n' >&2
      return 1
    }
    source="$anchor"
  else
    [ -n "$expected" ] && [ "$(codex_hash_file "$manifest")" = "$expected" ] || {
      printf 'codex: frozen contract manifest changed during the run.\n' >&2
      return 1
    }
    source="$manifest"
  fi

  while IFS=' ' read -r kind hash rel extra || [ -n "${kind:-}" ]; do
    [ -z "${extra:-}" ] || { printf 'codex: malformed frozen contract entry.\n' >&2; return 1; }
    case "$rel" in
      base_commit|task.md|allowlist|test|plan_dir|plan-id|test_source|workdir) ;;
      *) printf 'codex: unexpected frozen contract member: %s\n' "$rel" >&2; return 1 ;;
    esac
    [ -z "${seen[$rel]+_}" ] || { printf 'codex: duplicate frozen contract member: %s\n' "$rel" >&2; return 1; }
    seen[$rel]=1
    count=$((count + 1))
    case "$kind" in
      F)
        [ -f "$rundir/$rel" ] || { printf 'codex: frozen contract member is missing: %s\n' "$rel" >&2; return 1; }
        actual="$(codex_hash_file "$rundir/$rel")" || return 1
        [ "$actual" = "$hash" ] || { printf 'codex: frozen contract member changed: %s\n' "$rel" >&2; return 1; }
        ;;
      M)
        [ "$hash" = "-" ] && [ ! -e "$rundir/$rel" ] || {
          printf 'codex: frozen contract member appeared unexpectedly: %s\n' "$rel" >&2
          return 1
        }
        ;;
      *) printf 'codex: malformed frozen contract state for %s\n' "$rel" >&2; return 1 ;;
    esac
  done <"$source"
  [ "$count" -eq "${#CODEX_CONTRACT_FILES[@]}" ] || {
    printf 'codex: frozen contract manifest is incomplete.\n' >&2
    return 1
  }
}

# codex_meta_fingerprint <plandir>
# A single hash over every file in ONE plan directory. Compared across a Codex
# run to prove Codex did not rewrite its own instructions — most importantly
# its own allowlist, which it could otherwise widen and then pass the scope
# gate.
#
# Scoped to the plan being run, not to all of .codex-instructions/: a second
# agent working a different plan in the same repository would otherwise trip
# this check, and reporting "Codex tampered with the plan" for someone else's
# hint file is a false alarm that trains you to ignore a real one.
codex_meta_fingerprint() {
  local d="$1" f key i j
  local LC_ALL=C
  local files=()
  if [ ! -d "$d" ]; then printf 'absent\n'; return 0; fi
  # Bind normalized relative paths independently of the hash backend's output
  # format. NUL delimiters keep file names containing whitespace or newlines
  # unambiguous. An in-shell insertion sort avoids GNU-only `sort -z`.
  (
    cd "$d" || exit 1
    while IFS= read -r -d '' f; do files+=("$f"); done < <(find . -type f -print0)
    for ((i = 1; i < ${#files[@]}; i++)); do
      key="${files[$i]}"
      j=$((i - 1))
      while [ "$j" -ge 0 ] && [[ "${files[$j]}" > "$key" ]]; do
        files[$((j + 1))]="${files[$j]}"
        j=$((j - 1))
      done
      files[$((j + 1))]="$key"
    done
    for f in "${files[@]}"; do
      printf '%s\0%s\0' "$f" "$(codex_hash_file "$f")"
    done
  ) | "${CODEX_HASH[@]}" | cut -d' ' -f1
}

# codex_thread_id <events.jsonl>
# Best-effort extraction of the session id a resume needs. Key names have
# changed across Codex releases, so several are tried; an empty result means
# the caller must fall back rather than guess.
codex_thread_id() {
  local f="$1" id=""
  [ -f "$f" ] || return 0
  local key
  for key in thread_id session_id conversation_id rollout_id; do
    id="$(grep -o "\"$key\"[[:space:]]*:[[:space:]]*\"[^\"]\+\"" "$f" 2>/dev/null \
          | head -1 | sed 's/.*"\([^"]*\)"$/\1/')"
    [ -n "$id" ] && { printf '%s\n' "$id"; return 0; }
  done
  return 0
}

# codex_timeout_prefix <seconds>
# Emits a `timeout` invocation when the coreutils binary is present, and
# nothing when it is not — an unattended run should not die on a missing tool,
# but it also should not hang forever when one is available.
codex_timeout_prefix() {
  local secs="$1"
  [ -n "$secs" ] && [ "$secs" != "0" ] || return 0
  if command -v timeout >/dev/null 2>&1; then
    printf 'timeout\n%s\n' "$secs"
  fi
}
