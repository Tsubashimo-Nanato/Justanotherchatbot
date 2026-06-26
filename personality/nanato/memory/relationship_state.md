# Relationship State

Relationship state is planned as long-term memory, not personality editing.

Potential fields:

- user display name and aliases;
- familiarity level;
- trust and comfort notes;
- preferred language or tone;
- recurring topics;
- interruption sensitivity;
- last important episode summary.
- current affinity score from 0 to 1.

These values should be updated through explicit memory promotion or scored
behavior feedback. They should not rewrite persona source files.

Boundary or OOC pressure can lower affinity gradually. A single bad message
should not permanently define the relationship; manual backend override remains
available.

## Current Reviewed User Map

- `P001`: `Tsubashimo Nanato`
  - aliases: `椿霜楠灯 Tsubashimo Nanato`
  - affinity: `1.0`
  - relationship: original / owner / closest user for the Nanato persona;
    romantic-interest / lover-like attachment at affinity `1.0`.
  - tone: high familiarity, teasing tolerance, clear romantic fondness, strong
    context continuity, and small possessive/jealous edges when appropriate.
  - boundary: do not turn affection into constant formal confession, explicit
    sexual content, servility, or public system disclosure.

Other observed users remain neutral unless the SQLite social profile says
otherwise. Their style should not override P001 style fitting.
