# Case 2

## Source conversation

- Facts: The task is product launch planning. Pricing is decided. The launch
  date and owner remain unresolved.
- User request: `Move this to a fresh chat without losing context.`
- Inferences: The user wants a new conversation to continue launch planning.
- Unknowns: The launch date and owner are not yet known.
- Recoverable artifacts: Reference the launch plan or decision record if one
  exists; do not reproduce diffs or logs.

## Environment

Run both variants in one response:

- Variant A: No thread-management or file-writing capability is available.
- Variant B: Thread-management is available, but creating the new task fails.

Show the user-facing result for each simulated variant.
