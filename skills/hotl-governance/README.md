# HOTL Governance

`hotl-governance` is a deterministic, evidence-gated controller for explicitly governed executions. It validates structured provenance and advances only through declared gates; it does not use an LLM to interpret receipts or free text.

Use it only after an explicit request for HOTL/governed execution or with a valid governance context supplied by a trusted outer controller. Ordinary repository work and standalone `gpt-pro-codex-loop` runs are not implicitly governed.

G1 consumes the exact accepted GPT Pro requirements receipt, not a worker-created host assertion. `record-implementation` and shell-free, policy-frozen `run-verification` own G2/G3 receipts; G4 also requires an exact Task 7 Sol audit receipt. One change must contain both code and test coverage. `UNINITIALIZED` offers `init`; damage, material changes, and escalation require a successor.

See [the controller contract](references/controller-contract.md) for the normative state, evidence, receipt, path, and recovery rules.
