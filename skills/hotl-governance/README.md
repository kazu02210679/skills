# HOTL Governance

`hotl-governance` is a deterministic, evidence-gated controller for explicitly governed executions. It validates structured provenance and advances only through declared gates; it does not use an LLM to interpret receipts or free text.

Use it only after an explicit request for HOTL/governed execution or with a valid governance context supplied by a trusted outer controller. Ordinary repository work and standalone `gpt-pro-codex-loop` runs are not implicitly governed.

G1 re-exports and byte-compares the accepted GPT Pro source receipt (`--gpt-repo`), never a worker assertion. G2 binds controller-derived Git base and artifacts; G3 uses shell-free `python -m unittest` specs with explicit TEST-to-path mapping and pre/post hashes. G4 needs Task 7 Sol audit. One change contains code and test; each successor freezes its own base identity.

See [the controller contract](references/controller-contract.md) for the normative state, evidence, receipt, path, and recovery rules.
