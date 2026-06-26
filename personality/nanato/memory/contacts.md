# Contacts

Contacts are profile-owned relationship records. They belong in this character
folder, not in root `workspace/`.

Runtime contact truth currently lives in SQLite relationship memories under
`personality/nanato/memory/runtime/agent_memory.sqlite3`.

Planned contact fields:

- stable display name;
- aliases;
- platform-specific id when available;
- affinity score;
- current relationship notes;
- language and tone preference;
- boundaries or sensitive patterns;
- last meaningful interaction summary.

Contact files may be used later as reviewed exports or seed data. Runtime writes
should go through SQLite first so they remain auditable and can be overridden.

## Reviewed Contact IDs

- `P001`: `Tsubashimo Nanato`
  - aliases: `椿霜楠灯 Tsubashimo Nanato`
  - affinity: `1.0`
  - note: target user for current style fitting and Nanato's persona-specific
    original/owner relationship, with clear romantic / lover-like attachment.

Use these PIDs in handoffs and distillation notes so future agents can refer to
users without confusing display-name variants.
