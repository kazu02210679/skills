# Shared skills

This repository is the canonical source for reusable agent skills.

- Discover skills from the YAML frontmatter in `skills/*/SKILL.md`.
- When a task names or clearly matches a skill, read that `SKILL.md` completely before acting.
- Load linked references only when the selected skill requires them; do not load the full catalog.
- Edit the canonical file under `skills/`. Treat `.agents/skills/` and `.claude/skills/` as installed copies.
- Keep a concise human-facing `README.md` beside each canonical `SKILL.md`.
- Generate the root catalog from Skill frontmatter with `python scripts/generate-skill-catalog.py`; do not hand-edit the generated section.
- Preserve factual accuracy, safety constraints, and attribution when improving a skill.
- Install `requirements-validation.txt`, then run `python scripts/validate-skills.py` and the focused tests after changing Skill or installer files.
- For behavior changes, add or update a focused evaluation before accepting an optimization.
- Apply the host semantics and slash-command mappings in `docs/host-compatibility.md`; do not claim full Codex/Claude runtime parity.

This repository contains only the maintained catalog under `skills/`. Do not vendor external
Skill collections into that directory. Keep the `handoff` attribution files under
`third_party/handoff-gist/` with every redistributed copy.
