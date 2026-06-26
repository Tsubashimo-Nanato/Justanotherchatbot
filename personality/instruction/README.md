# Persona Instruction Index

This folder is for agents that maintain persona files across all personas.
It is not runtime persona text and should not be loaded into the chatbot prompt.

## Current Persona Example

The current active persona is `nanato`. Its runtime persona config is defined in
`config/persona.yaml`.

For Nanato, the currently loaded profile documents are:

- `personality/nanato/profile/distilled_anchor.md`
- `personality/nanato/profile/generated_style_anchor.md`
- `personality/nanato/profile/style_learning_objective.md`
- `personality/nanato/profile/runtime_boundaries.md`

Future personas should follow the same structure: each persona owns its own
`profile/`, `memory/`, and `workspace/`, while this shared `instruction/`
folder explains how persona agents should maintain them.

Persona runtime memory is separate from these active profile documents. For
Nanato, persona-specific memory and user/profile state live under
`personality/nanato/memory/` and the runtime SQLite store owned by that folder.
Do not move these files into the root project workspace.

## What Each File Is For

- `style_distillation.md`: how to distill a user's speaking style.
- `manual_profile_edits.md`: how to edit persona and long-term memory by hand.
- `token_budget_and_compression.md`: how to keep persona files small.
- `distillation_agent_handoff.md`: checklist for an external distillation agent.
- `qa_and_smoke.md`: how a distillation agent should inspect logs and test changes.
- `runtime_and_encoding_hygiene.md`: how to avoid service-process conflicts and
  mojibake-driven persona corruption.

## User Identity Rule

Every style distillation target must be identified by the exact display name
from the user's social profile or persona-owned user profile. The name must be
written in the output style anchor, for example:

```text
Target user: Tsubashimo Nanato
```

Do not distill an unnamed "user", "owner", "tester", or inferred identity.
If the target user is unclear, stop and ask for the exact profile name.

When a handoff assigns a PID, keep it as a stable discussion handle and still
write the exact display name in files. Example:

```text
P001 = Tsubashimo Nanato
aliases = 椿霜楠灯 Tsubashimo Nanato
```

The PID is only for agent-to-agent coordination. Runtime-facing persona text and
memory proposals should use the real display name when referring to a person.

## Boundary

Style distillation is about how a person speaks: rhythm, punctuation, grammar,
tone, topic handling, impatience, warmth, mistakes, and conversational habits.
It is not a memory import. Do not copy personal events, schedules, allergies,
private facts, or raw chat logs into style anchors.

## Local-First Runtime Rule

The current harness is local-first. The local model should receive compact
persona guidance and enough recent context to decide whether to reply, what the
user means, and whether a tool is needed. Distillation must therefore improve
the model's reusable conversational priors, not add more brittle command
patterns or fixed answer templates.

When updating a persona for local-first runtime:

- keep core identity short;
- keep learned style in `generated_style_anchor.md`;
- keep relationship rules scoped to the exact user profile they belong to;
- write negative feedback as reusable constraints, not as copied incidents;
- preserve dry humor, impatience, bluntness, and semantic follow-up handling
  when those are real target-user traits;
- avoid global tenderness or generic comfort-bot language unless it is actually
  part of the target style.

## Encoding Rule

All persona and instruction files are UTF-8. Windows PowerShell or terminal
output may display Chinese/Japanese text as mojibake even when the file is fine.
Before changing persona text because it "looks garbled", verify whether the
stored file is actually corrupt:

- read files with an explicit UTF-8 path, for example Python
  `Path(...).read_text(encoding="utf-8")`;
- inspect SQLite values through Python or a UTF-8-aware DB tool;
- do not use a garbled terminal rendering as source truth;
- if storage is clean and only the console is wrong, leave persona text alone;
- if storage is truly mojibake, repair only from known-good source material or
  a backup. Do not invent missing text from corrupted bytes.
