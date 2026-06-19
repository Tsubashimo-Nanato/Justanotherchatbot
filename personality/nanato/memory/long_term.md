# Long-Term Memory

Long-term memory stores stable summaries that should survive model changes.
It lives in SQLite `memories` and is independent from the current GGUF model.

Memory classes:

- `profile`: stable facts about the configured character runtime, not persona source text.
- `relationship`: per-user relationship and familiarity notes.
- `preference`: user preferences and recurring conversation choices.
- `taboo`: boundaries or avoided behaviors.
- `episode`: notable past interactions worth remembering.
- `procedural`: stable operating preferences.
- `behavior_feedback`: reviewed score feedback about previous replies.
- `working_context`: durable context summaries that are not personality.

Promotion rule: short-term events become long-term memories only when they are
explicitly requested, repeated, scored, or clearly stable.
