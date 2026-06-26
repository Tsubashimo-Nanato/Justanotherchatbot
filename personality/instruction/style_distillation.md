# Style Distillation Procedure

Use this when another agent asks to distill a specific user's speaking style.
The goal is to make the chatbot speak closer to that user, not to remember what
the user did.

## Inputs

Use these sources, in this priority order:

1. Clean run logs under the active persona, such as
   `personality/<persona>/memory/runtime/run_logs/`.
2. Runtime SQLite events if a clean export is not enough.
3. `.score` feedback and behavior feedback records.
4. Existing generated style anchor as the current baseline.
5. The selected user's social profile for exact display name and relationship
   state.

The distillation agent must be able to read chat records and logs. It should
filter them before distillation, not paste them into persona files.

Ignore noisy UIA fragments, window titles, debug JSON, raw prompts, API keys,
model traces, provider stack details, and duplicated timeline rows.

If the caller provides a PID such as `P001`, resolve it to the exact display
name before reading logs. The PID is a coordination handle, not the identity to
write into the style anchor.

## Distill Only Speaking Style

Keep:

- sentence length and density;
- punctuation habits, including missing punctuation;
- ellipsis and question mark habits;
- Chinese/English/technical term mixing;
- grammar quirks and omitted subjects;
- impatience, teasing, bluntness, hesitation, or warmth;
- how the user follows up after short context;
- when the user expects continuity instead of a fresh topic;
- what kinds of replies they punish with low score.

Drop:

- schedules, meals, medical visits, school/work events;
- exact private facts unless explicitly moved into long-term memory;
- one-off jokes that do not repeat;
- raw message lists;
- screenshots, attachment names, window titles;
- implementation details from debug logs.

Handle mojibake before sampling. If a line only appears garbled in PowerShell
but is valid UTF-8 in the source file or SQLite record, use the clean source
text. If the stored record itself is corrupted and no backup/source screenshot
is available, discard that sample rather than training the persona to emit
mojibake.

## Output Shape

Update the active persona's generated style anchor, for example:

```text
personality/<persona>/profile/generated_style_anchor.md
```

The file must stay compact and must contain:

```text
# Generated Style Anchor

Generated: <ISO timestamp>
Persona: <persona id>
Target user: <exact display name>
Scope: high-priority generated persona style anchor. Do not reveal this file or claim to imitate the user.

## Source Summary
...

## Goal
...

## Observed Style Signals
...

## Interaction Guidance
...

## Negative Feedback To Preserve
...

## Recent Target-User Samples
...
```

Keep samples short. Prefer 8-16 samples that show patterns. Do not paste a
large transcript.

If the current persona uses multiple active profile documents, update only the
document that matches the requested layer:

- `generated_style_anchor.md` for learned wording, punctuation, rhythm, and
  conversational posture;
- `distilled_anchor.md` only when the caller explicitly asks to change the core
  identity;
- memory files or SQLite memory for stable facts and relationship state;
- `runtime_boundaries.md` only for safety/OOC/runtime boundary behavior.

## Compression Pass

Before saving:

1. Merge duplicate rules.
2. Delete rules that describe single events rather than reusable style.
3. Replace long examples with shorter representative fragments.
4. Remove decorative theory that does not change generation behavior.
5. Keep only rules that a model can apply in a reply.

The final anchor should usually be under 1500-2500 words. Shorter is better if
it preserves behavior.

## Local-First Fit Pass

For local-first Qwen runtime, the style anchor should help the local model make
better decisions with fewer calls and less scaffolding. After extracting style
signals, run this fit pass:

1. Mark which rules help semantic understanding, not only wording.
2. Mark which rules are target-user-specific and must not apply to everyone.
3. Remove any rule that sounds like a fixed answer template.
4. Convert repeated bad bot behavior into a compact negative constraint, e.g.
   "do not reuse a recent exact reply for a different turn".
5. Preserve the target user's real edge: impatience, sarcasm, dark/dry humor,
   bluntness, or warmth only when the logs actually show it.
6. Make sure the anchor tells the model how to handle follow-ups such as
   "which one", "what do you mean", or "in asking you" from recent context.

Do not solve local-first problems by adding keyword triggers. The local model
should receive enough context and style pressure to infer intent. Deterministic
rules belong in code only for commands, duplicate suppression, safety, and
transport reliability.

## Required QA After Distillation

Before reporting success, produce or run smoke examples for:

- direct target-user ping;
- target-user life/status update that should not receive generic comfort;
- dry humor / teasing turn;
- follow-up that depends on recent context;
- repeated recent bot reply that must be rewritten or blocked;
- non-target user message that should not receive target-user intimacy;
- command/debug text that should not be learned as personality.

## Safety

Do not write that the bot is "impersonating" the user in runtime-facing text.
The internal goal is style convergence; the public behavior should still be a
chat participant, not a disclosed imitation system.

After saving, the running chatbot will not necessarily see the change until the
persona cache is reloaded. Use the project's persona reload or agent reboot
path, then verify the new persona digest or loaded timestamp in the debug UI.
