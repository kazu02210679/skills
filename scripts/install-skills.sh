#!/usr/bin/env bash
set -Eeuo pipefail

agent="both"
scope="user"
project_root="$PWD"
replace_existing=0

usage() {
  cat >&2 <<'EOF'
Usage: install-skills.sh [--agent codex|claude|both] [--scope user|project]
                         [--project-root PATH] [--force|--replace]

Existing managed Skill or notice directories are conflicts. Use --force (or
--replace) to replace complete managed directories transactionally.
EOF
}

require_value() {
  local option="$1"
  local count="$2"
  if [[ "$count" -lt 2 ]]; then
    echo "Missing value for $option" >&2
    usage
    exit 2
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --agent)
      require_value "$1" "$#"
      agent="$2"
      shift 2
      ;;
    --scope)
      require_value "$1" "$#"
      scope="$2"
      shift 2
      ;;
    --project-root)
      require_value "$1" "$#"
      project_root="$2"
      shift 2
      ;;
    --force|--replace)
      replace_existing=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [[ "$agent" != "codex" && "$agent" != "claude" && "$agent" != "both" ]]; then
  echo "--agent must be codex, claude, or both" >&2
  exit 2
fi
if [[ "$scope" != "user" && "$scope" != "project" ]]; then
  echo "--scope must be user or project" >&2
  exit 2
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repository_root="$(cd "$script_dir/.." && pwd)"
source_root="$repository_root/skills"
notices_root="$repository_root/third_party"
compatibility_source="$repository_root/docs/host-compatibility.md"

if [[ ! -d "$source_root" ]]; then
  echo "Skills directory not found: $source_root" >&2
  exit 1
fi

skill_names=()
for skill in "$source_root"/*; do
  [[ -d "$skill" ]] || continue
  skill_name="$(basename "$skill")"
  if [[ ! -f "$skill/SKILL.md" ]]; then
    echo "Invalid source Skill $skill_name: missing SKILL.md" >&2
    exit 1
  fi
  skill_names+=("$skill_name")
done
if [[ "${#skill_names[@]}" -eq 0 ]]; then
  echo "No Skill directories found in $source_root" >&2
  exit 1
fi

for source_name in pm-skills handoff-gist; do
  for filename in LICENSE source.json SHA256SUMS; do
    if [[ ! -f "$notices_root/$source_name/$filename" ]]; then
      echo "Required notice file is missing: $source_name/$filename" >&2
      exit 1
    fi
  done
done
if [[ ! -f "$compatibility_source" ]]; then
  echo "Required compatibility notice is missing: $compatibility_source" >&2
  exit 1
fi

if [[ "$scope" == "user" ]]; then
  base_root="${HOME:?HOME is not set}"
else
  if [[ ! -d "$project_root" ]]; then
    echo "Project root does not exist: $project_root" >&2
    exit 1
  fi
  # Keep a relative root relative on MSYS. Re-expanding it through `pwd` turns
  # it into a POSIX /c path, which can defeat Windows filesystem sandboxes.
  base_root="$project_root"
fi

destinations=()
if [[ "$agent" == "codex" || "$agent" == "both" ]]; then
  destinations+=("$base_root/.agents/skills")
fi
if [[ "$agent" == "claude" || "$agent" == "both" ]]; then
  destinations+=("$base_root/.claude/skills")
fi

target_names=("${skill_names[@]}" ".third-party-notices")
for destination_root in "${destinations[@]}"; do
  for target_name in "${target_names[@]}"; do
    target="$destination_root/$target_name"
    if [[ -e "$target" || -L "$target" ]]; then
      if [[ "$replace_existing" -ne 1 ]]; then
        echo "Installation conflict: $target already exists. Re-run with --force to replace managed directories." >&2
        exit 3
      fi
    fi
  done
done

transactions=()
stages=()
backups=()

cleanup_transactions() {
  local transaction
  for transaction in "${transactions[@]:-}"; do
    if [[ -n "$transaction" && -d "$transaction" ]]; then
      rm -rf -- "$transaction"
    fi
  done
}
trap cleanup_transactions EXIT

compare_trees() {
  local source="$1"
  local staged="$2"
  if ! diff -qr -- "$source" "$staged" >/dev/null; then
    echo "Staged copy verification failed: $source" >&2
    return 1
  fi
}

for destination_root in "${destinations[@]}"; do
  destination_parent="$(dirname "$destination_root")"
  mkdir -p "$destination_parent"
  transaction="$(mktemp -d "$destination_parent/.skills-install-XXXXXXXX")"
  stage="$transaction/stage"
  backup="$transaction/backup"
  mkdir -p "$stage" "$backup" "$transaction/touched" "$transaction/created"
  transactions+=("$transaction")
  stages+=("$stage")
  backups+=("$backup")

  for skill_name in "${skill_names[@]}"; do
    cp -a -- "$source_root/$skill_name" "$stage/$skill_name"
    compare_trees "$source_root/$skill_name" "$stage/$skill_name"
  done

  notice_stage="$stage/.third-party-notices"
  mkdir -p "$notice_stage/pm-skills" "$notice_stage/handoff-gist"
  for source_name in pm-skills handoff-gist; do
    for filename in LICENSE source.json SHA256SUMS; do
      cp -a -- \
        "$notices_root/$source_name/$filename" \
        "$notice_stage/$source_name/$filename"
      cmp -s -- \
        "$notices_root/$source_name/$filename" \
        "$notice_stage/$source_name/$filename" || {
          echo "Staged notice verification failed: $source_name/$filename" >&2
          exit 1
        }
    done
  done
  cp -a -- "$compatibility_source" "$notice_stage/HOST-COMPATIBILITY.md"
  cmp -s -- \
    "$compatibility_source" \
    "$notice_stage/HOST-COMPATIBILITY.md" || {
      echo "Staged compatibility notice verification failed" >&2
      exit 1
    }

done

rollback() {
  local original_status="$1"
  trap - ERR INT TERM
  set +e
  local index target_name destination_root transaction backup
  for ((index=${#destinations[@]}-1; index>=0; index--)); do
    destination_root="${destinations[$index]}"
    transaction="${transactions[$index]}"
    backup="${backups[$index]}"
    for target_name in "${target_names[@]}"; do
      if [[ ! -f "$transaction/touched/$target_name" ]]; then
        continue
      fi
      if [[ -e "$backup/$target_name" || -L "$backup/$target_name" ]]; then
        rm -rf -- "$destination_root/$target_name"
        mv -- "$backup/$target_name" "$destination_root/$target_name"
      elif [[ -f "$transaction/created/$target_name" ]]; then
        rm -rf -- "$destination_root/$target_name"
      fi
    done
  done
  echo "Installation failed; all touched targets were rolled back." >&2
  exit "$original_status"
}

trap 'rollback $?' ERR
trap 'rollback 130' INT
trap 'rollback 143' TERM

mutation_count=0
backup_attempt_count=0
for index in "${!destinations[@]}"; do
  destination_root="${destinations[$index]}"
  stage="${stages[$index]}"
  backup="${backups[$index]}"
  transaction="${transactions[$index]}"
  mkdir -p "$destination_root"

  for target_name in "${target_names[@]}"; do
    touch "$transaction/touched/$target_name"
    if [[ -e "$destination_root/$target_name" || -L "$destination_root/$target_name" ]]; then
      backup_attempt_count=$((backup_attempt_count + 1))
      if [[ -n "${SKILLS_INSTALL_TEST_FAIL_BEFORE_BACKUP_AFTER:-}" ]] &&
         [[ "$backup_attempt_count" -ge "$SKILLS_INSTALL_TEST_FAIL_BEFORE_BACKUP_AFTER" ]]; then
        echo "Injected installer failure before backup $backup_attempt_count." >&2
        false
      fi
      mv -- "$destination_root/$target_name" "$backup/$target_name"
    else
      touch "$transaction/created/$target_name"
    fi
    mv -- "$stage/$target_name" "$destination_root/$target_name"
    mutation_count=$((mutation_count + 1))
    if [[ -n "${SKILLS_INSTALL_TEST_FAIL_AFTER:-}" ]] &&
       [[ "$mutation_count" -ge "$SKILLS_INSTALL_TEST_FAIL_AFTER" ]]; then
      echo "Injected installer failure after $mutation_count target(s)." >&2
      false
    fi
  done
done

trap - ERR INT TERM
for destination_root in "${destinations[@]}"; do
  echo "Installed ${#skill_names[@]} skills and third-party notices to $destination_root"
done
