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
