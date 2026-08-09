# HOTL Governance

`hotl-governance` is a deterministic, evidence-gated controller for explicitly governed executions. It validates structured provenance and advances only through declared gates; it does not use an LLM to interpret receipts or free text.

Use it only after an explicit request for HOTL/governed execution or with a valid governance context supplied by a trusted outer controller. Ordinary repository work and standalone `gpt-pro-codex-loop` runs are not implicitly governed.

Authority remains bounded by the frozen scope, policy, and approval receipts. Generic records cannot impersonate privileged approval, and malformed or ambiguous state fails closed. `RECOVERY_REQUIRED`, material changes to frozen artifacts, and escalation end the current execution; preserve its evidence and begin an authorized successor instead of repairing or continuing it.

See [the controller contract](references/controller-contract.md) for the normative state, evidence, receipt, path, and recovery rules.
