# Shared skills

This repository is the canonical source for reusable agent skills.

- Discover skills from the YAML frontmatter in `skills/*/SKILL.md`.
- When a task names or clearly matches a skill, read that `SKILL.md` completely before acting.
- Load linked references only when the selected skill requires them; do not load the full catalog.
- Edit the canonical file under `skills/`. Treat `.agents/skills/` and `.claude/skills/` as installed copies.
- Preserve factual accuracy, safety constraints, and attribution when improving a skill.
- Run `python scripts/validate-skills.py` after changing skill files.
- For behavior changes, add or update a focused evaluation before accepting an optimization.

The `pm-skills` entries were imported from `phuryn/pm-skills` 2.1.0 under the MIT license. Keep
`third_party/pm-skills/LICENSE` and `third_party/pm-skills/source.json` with redistributed copies.
