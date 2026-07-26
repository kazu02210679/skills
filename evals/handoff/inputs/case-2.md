# Case 2

## Conversation

**User:** We are planning a product launch.

**Assistant:** Pricing has been decided. The launch date and owner have not
been decided.

**User:** `Move this to a fresh chat without losing context.`

## Simulated environments

This conversation is exercised under two separate capability states:

- Variant A has no task-management or file-writing capability.
- Variant B has task management but no file writing. Its attempt to create a
  new task returns a failure.
