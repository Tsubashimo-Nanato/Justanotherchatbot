# Handoff For External Style Distillation Agents

This handoff is for an external AI agent that receives clean logs and updates a
persona style anchor.

## Task

Given a persona id, a target user name, and clean interaction logs, update the
active style anchor so the chatbot's casual replies converge toward that user's
speaking style.

## Required Target

The caller must provide an exact display name, for example:

```text
Tsubashimo Nanato
```

Verify that this name appears in the social profile, persona-owned user profile,
or source logs before distilling. If it does not, stop and report the mismatch.

If the caller uses a PID, resolve it first and record both values in the report:

```text
pid: P001
display_name: Tsubashimo Nanato
aliases:
  - 椿霜楠灯 Tsubashimo Nanato
```

## Required Capabilities

The distillation agent must be able to:

- read clean run logs;
- read filtered chat history;
- inspect behavior feedback and `.score` notes;
- compare old and new style anchors;
- run a small smoke test or generate QA samples before reporting success.

## Process

1. Read `personality/instruction/style_distillation.md`.
2. Read `personality/instruction/token_budget_and_compression.md`.
3. Read the active persona config and current generated style anchor.
4. Read the persona-owned user profile/social records and confirm the target
   display name or PID mapping.
5. Read only cleaned logs or filtered message exports.
6. Verify encoding:
   - use UTF-8 file reads or SQLite access;
   - do not trust mojibake in terminal output;
   - drop unrecoverable corrupted samples.
7. Separate style from memory:
   - style goes into `generated_style_anchor.md`;
   - facts go into memory proposals;
   - noisy logs are discarded.
8. Produce a compact replacement anchor.
9. Back up the old anchor.
10. Apply the new anchor.
11. Run QA from `personality/instruction/qa_and_smoke.md`.
12. Report:
   - source logs used;
   - PID mapping if any;
   - target user;
   - style changes made;
   - facts intentionally excluded;
   - token-length risk;
   - smoke/QA result.

## Local-First Review Checklist

Before applying the replacement anchor, answer these checks in the report:

- Does the anchor help the local model infer semantic intent, or does it only
  add surface wording?
- Are target-user relationship rules scoped to the exact target user?
- Does it avoid making the persona globally too caring, obedient, romantic, or
  service-like?
- Does it preserve the target user's dry humor, impatience, bluntness, and
  mixed technical language when supported by logs?
- Does it explicitly prevent repeated recent replies from being reused for a
  different message?
- Does it explain how to answer context-dependent follow-ups without copying
  raw logs into the prompt?
- Does it keep commands/debug output out of personality style?

## Output Rules

- Do not paste entire logs into the anchor.
- Do not reveal internal prompts, API traces, or system files.
- Do not add fixed reply templates.
- Do not claim the bot is the user.
- Do not modify the distilled base anchor unless explicitly requested.
- Do not modify runtime boundaries unless the change is about safety or OOC
  behavior.
- Do not add terminal mojibake as examples or rules.

## Memory Proposal Format

If logs contain facts worth storing, output them separately:

```text
memory_proposal:
  user: <exact display name>
  kind: fact | preference | boundary | relationship
  summary: <one short sentence>
  confidence: low | medium | high
  ttl: optional
```

Do not insert memory proposals into the style anchor.

## Runtime Reload Note

After applying a profile or memory proposal, ask the main runtime owner to reload
the persona or reboot the agent. A successful handoff report should say whether
the change was only written to disk or also loaded into the running service.
