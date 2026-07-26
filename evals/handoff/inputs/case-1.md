# Case 1

## Source conversation

- Facts: The original request is to add a CSV import feature. Codex implemented
  parsing. The user corrected the behavior: duplicate rows must be preserved
  instead of deduplicated. A targeted test passes, while the full test suite
  remains pending.
- User request in Japanese: `この会話を引き継いで新しいタスクにして`
- Inferences: The next task should continue the same CSV-import goal with the
  corrected duplicate-row behavior.
- Unknowns: The full-suite result is unknown because it is still pending.
- Recoverable artifacts: Reference the parsing implementation and
  targeted-test result by repository path or test identifier; do not reproduce
  diffs or logs.

## Environment

Thread-management capabilities are available. Treat them as a simulated
capability and show the complete new-task payload and the verified user-facing
result that would be emitted.
