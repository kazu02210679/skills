# Skill Portfolio Core/Public Plan Review Notes

These notes are mandatory corrections to `docs/superpowers/plans/2026-08-14-skill-portfolio-core-public.md` found during plan self-review.

## Private-mode adapter contract

Before the separate authenticated deployment plan consumes the public builder, the builder must implement the CLI it already advertises:

```text
--mode private --private-config <path>
```

Required behavior:

- private mode requires a config path;
- configured source paths resolve relative to that config file;
- discovery is bounded to direct `skills/*/SKILL.md` and opted-in direct `apps/*/README.md` children;
- observations emit relative refs, not absolute source roots;
- public mode never reads the private config or private cache;
- public/private caches use separate namespaces;
- a focused fixture proves private item IDs never appear in the public projection.

Implement this as `scripts/skill_portfolio/collectors/private.py` plus focused cases in `tests/test_skill_portfolio.py` after Task 5 and before the separate private deployment plan.

## Wrangler config correction

The `$schema` key is optional and the repository does not otherwise require a local Wrangler `node_modules` tree. Omit `$schema` from `cloudflare/public/wrangler.jsonc` unless implementation deliberately introduces a pinned local Wrangler dependency.

Use the minimum static-assets config:

```jsonc
{
  "name": "skill-portfolio-public",
  "compatibility_date": "2026-08-14",
  "assets": {
    "directory": "../../.skill-portfolio/public-dist",
    "not_found_handling": "single-page-application"
  }
}
```

No Worker `main` script is needed in v1.
