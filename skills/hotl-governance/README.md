# HOTL Governance

`hotl-governance` is a deterministic, evidence-gated controller for explicitly governed executions. It validates structured provenance and advances only through declared gates; it does not use an LLM to interpret receipts or free text.

Use it only after an explicit request for HOTL/governed execution or with a valid governance context supplied by a trusted outer controller. Ordinary repository work and standalone `gpt-pro-codex-loop` runs are not implicitly governed.

The approved v2b reduction changes behavior and the public contract, invalidates prior closure evidence, and resets review. GPT and Sol receipts and local unittest results are canonical audit artifacts, not gate authority. Valid imports and local verification may be stored for integrity and replay diagnostics, but the current production build has no caller-independent host/CI provenance provider and exposes no provider selector or grant hook. G1, G3, G4, STOP, and MATERIAL_CHANGE therefore fail closed; no current execution can reach production completion. G2 still checks the controller-derived Git base and exact artifacts without establishing authority. Verification fixes `sys.executable`, explicit TEST-to-path mappings, pre/post hashes, and a full Git-visible repository snapshot digest. Sol advice is optional and cannot change the underlying decision.

See [the controller contract](references/controller-contract.md) for the normative state, evidence, receipt, path, and recovery rules.
