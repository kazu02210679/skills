#!/usr/bin/env bash
set -euo pipefail

agent="both"
scope="user"
project_root="$PWD"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --agent)
      agent="$2"
      shift 2
      ;;
    --scope)
      scope="$2"
      shift 2
      ;;
    --project-root)
      project_root="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
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

if [[ ! -d "$source_root" ]]; then
  echo "Skills directory not found: $source_root" >&2
  exit 1
fi

if [[ "$scope" == "user" ]]; then
  base_root="${HOME:?HOME is not set}"
else
  base_root="$(cd "$project_root" && pwd)"
fi

destinations=()
if [[ "$agent" == "codex" || "$agent" == "both" ]]; then
  destinations+=("$base_root/.agents/skills")
fi
if [[ "$agent" == "claude" || "$agent" == "both" ]]; then
  destinations+=("$base_root/.claude/skills")
fi

skill_count="$(find "$source_root" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ')"

for destination_root in "${destinations[@]}"; do
  mkdir -p "$destination_root"
  for skill in "$source_root"/*; do
    [[ -d "$skill" ]] || continue
    destination_skill="$destination_root/$(basename "$skill")"
    mkdir -p "$destination_skill"
    cp -R "$skill"/. "$destination_skill"/
  done
  echo "Installed $skill_count skills to $destination_root"
done
