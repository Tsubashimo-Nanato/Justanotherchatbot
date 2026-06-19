# Nanato Memory Layer

This folder is for runtime memory, context planning, and behavior feedback for
the Nanato profile. It is intentionally separate from the personality source
files. Personality defines stable identity and voice; memory records what the
agent has learned or recently experienced.

Runtime truth for the current demo is SQLite under
`personality/nanato/memory/runtime/agent_memory.sqlite3`.

## Boundaries

- Personality files describe stable character identity, voice, and world context.
- Memory files describe learned facts, recent context, relationship state, and behavior feedback.
- `.score` feedback must not rewrite personality files.
- Low scores should become behavior guidance, such as "do not interrupt this kind of exchange".
- High scores may reinforce a behavior pattern, but still do not change core identity.

## Memory Classes

- `short_term_context`: recent conversation turns, active topic, pending questions, and interruption risk.
- `long_term_facts`: stable user facts, preferences, recurring topics, and remembered mappings.
- `relationship_state`: affinity, trust, familiarity, and per-user conversational comfort.
- `behavior_feedback`: scored feedback about a previous reply, including what was wrong or useful.
- `boundaries`: topics or behaviors that should be avoided regardless of score.

## Runtime Mapping

Current `.score` commands write `behavior_feedback` events and memories into SQLite.
Low scores below `0.35` with a reason are also appended to `behavior_feedback.jsonl`
as review material for a separate personality agent. Runtime feedback still must
not rewrite personality files directly.

## Files

- `runtime/agent_memory.sqlite3`: current SQLite event, short-term context, and long-term memory store.
- `context.md`: human-readable plan for how context should be assembled before a reply.
- `short_term.md`: short-term memory retention rules.
- `long_term.md`: durable memory classes and promotion rules.
- `relationship_state.md`: planned per-user relationship fields.
- `mood.md`: global short-term mood and per-user affinity rules.
- `contacts.md`: planned contact index and per-user relationship export format.
- `capabilities.md`: how non-chat capabilities such as web lookup, calculation, and local scratch work should enter the reply pipeline.
- `behavior_feedback.jsonl`: low-score behavior feedback exports for later review; these records are not personality edits.

## SQLite Contents

The SQLite store is allowed to contain both short-term and long-term records:

- `events`: raw observed messages, agent decisions, tool results, placeholders, and reply events.
- `memories`: durable summaries such as remembered facts, user preferences, relationship notes, boundaries, and behavior feedback.

Temporary scratch files do not belong here. Scratch work should be created under
`personality/nanato/workspace/temp/`, recorded as an event if useful for the
current turn, then cleaned up.
