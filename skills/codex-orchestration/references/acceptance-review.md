# Acceptance review

Use this checklist after Codex reports that implementation is complete.

1. Read the task packet before the implementation report.
2. Map every acceptance item to a command, file inspection, or observable
   runtime result.
3. Run the real checks and record their exit status or concrete result.
4. Inspect the diff for work outside the packet, weakened tests, disabled
   checks, broad permission changes, and hidden generated artifacts.
5. Return a compact table with:
   - acceptance item;
   - command or evidence;
   - `PASS`, `FAIL`, or `UNRESOLVED`;
   - the shortest useful explanation.
6. Finish with one verdict:
   - `DELIVER` when every required item passes;
   - `SEND BACK` when a fix is needed;
   - `ASK USER` when the remaining decision requires new authority or a
     product choice.

Do not repair implementation code during this review. The orchestrator decides
whether to send a targeted hint or ask the user.
