# Shared skills

This repository is the canonical source for reusable agent skills.

- Discover skills from the YAML frontmatter in `skills/*/SKILL.md`.
- When a task names or clearly matches a skill, read that `SKILL.md` completely before acting.
- Load linked references only when the selected skill requires them; do not load the full catalog.
- Edit the canonical file under `skills/`. Treat `.agents/skills/` and `.claude/skills/` as installed copies.
- Preserve factual accuracy, safety constraints, and attribution when improving a skill.
- Install `requirements-validation.txt`, then run `python scripts/validate-skills.py` and the focused tests after changing Skill or installer files.
- For behavior changes, add or update a focused evaluation before accepting an optimization.
- Apply the host semantics and slash-command mappings in `docs/host-compatibility.md`; do not claim full Codex/Claude runtime parity.

The `pm-skills` entries were imported from `phuryn/pm-skills` 2.1.0 under the MIT license. Keep
their bodies byte-for-byte identical to `third_party/pm-skills/SHA256SUMS`. Keep each source's
`LICENSE`, `source.json`, and `SHA256SUMS` with redistributed copies.
